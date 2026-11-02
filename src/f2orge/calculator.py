"""Generate self-contained, offline HTML calculators from callable equations."""
from __future__ import annotations

import html
import json
from typing import Dict

from . import syntax as S
from .constants import CONSTANTS
from .dimensions import describe_full
from .errors import ForgeError, Source, UnitError
from .evaluator import ARITY, FUNCTIONS
from .evaluator import Scope
from .parser import parse
from .units import PREFIXES, Unit, all_unit_names, lookup_unit


def run_terminal_calculator(interpreter, equation_name: str, input_fn=input, out=print) -> None:
    """Run an assignment-driven calculator, recalculating after every valid input change."""
    eq = interpreter.equations[equation_name]
    out(f"{eq.name} calculator — enter input assignments; use :help or :quit.")
    if not eq.inputs:
        _print_terminal_outputs(eq, interpreter, {}, out)
        return
    values = {}
    while True:
        try:
            line = input_fn(f"{eq.name}> ")
        except EOFError:
            out("")
            return
        command = line.strip()
        if command in (":quit", ":q"):
            return
        if command == ":help":
            out("Enter one input assignment per line, such as m = 150 kg. "
                "Values are rechecked and outputs recalculate after each update.")
            out(f"Inputs: {', '.join(eq.inputs)}")
            continue
        if command == ":values":
            out(", ".join(f"{name} = {value}" for name, value in values.items()) or "(no values yet)")
            continue
        try:
            source = Source("<calculator>", line)
            statements = parse(source)
            if len(statements) != 1 or not isinstance(statements[0], S.Assign):
                raise ForgeError("enter one input assignment, such as m = 150 kg",
                                 title="Invalid calculator input")
            statement = statements[0]
            name = statement.name
            if name not in eq.inputs:
                raise ForgeError(
                    f"'{name}' is not an input of {eq.name}",
                    statement.span,
                    hint=f"Inputs: {', '.join(eq.inputs)}",
                    title="Invalid calculator input",
                )
            scope_values = dict(interpreter.variables)
            scope_values.update(values)
            quantity = interpreter.evaluator.eval(statement.expr, Scope(scope_values))
            decl = eq.decls.get(name)
            if decl is not None and decl.unit.dim != quantity.dim:
                raise UnitError(
                    f"{name} of {eq.name} expects {describe_full(decl.unit.dim)}, "
                    f"but this is {describe_full(quantity.dim)}",
                    statement.expr.span,
                    hint=f"{name} is declared as '{decl.unit.symbol()}'. Convert or correct the value.",
                )
            values[name] = quantity
            out(f"{name} = {quantity}")
            if len(values) == len(eq.inputs):
                _print_terminal_outputs(eq, interpreter, values, out)
        except ForgeError as err:
            out(err.format())


def _print_terminal_outputs(eq, interpreter, values, out) -> None:
    args = {name: (value, None) for name, value in values.items()}
    results = eq.call(interpreter.evaluator, args, None)
    for name in eq.outputs:
        out(f"{name} = {results[name]}")


def _dim_data(dim) -> list:
    return [float(exponent) for exponent in dim.exps]


def _unit_data(unit: Unit) -> Dict[str, object]:
    return {
        "dim": _dim_data(unit.dim),
        "scale": unit.scale,
        "offset": unit.offset,
        "label": unit.symbol(),
    }


def _expression_data(node) -> Dict[str, object]:
    if isinstance(node, S.Number):
        return {"kind": "number", "value": node.value}
    if isinstance(node, S.QuantityLit):
        return {"kind": "quantity", "value": node.value, "unit": _unit_data(node.unit)}
    if isinstance(node, S.Name):
        return {"kind": "name", "name": node.name}
    if isinstance(node, S.Unary):
        return {"kind": "unary", "op": node.op, "value": _expression_data(node.operand)}
    if isinstance(node, S.Binary):
        return {
            "kind": "binary", "op": node.op,
            "left": _expression_data(node.left), "right": _expression_data(node.right),
        }
    if isinstance(node, S.Call):
        return {
            "kind": "call", "name": node.func,
            "args": [_expression_data(arg) for arg in node.args],
            "kwargs": {name: _expression_data(value) for name, value, _ in node.kwargs},
        }
    if isinstance(node, S.Member):
        return {"kind": "member", "value": _expression_data(node.obj), "name": node.attr}
    raise ForgeError(f"cannot generate a calculator for expression {type(node).__name__}",
                     title="Calculator unavailable")


def _equation_data(eq) -> Dict[str, object]:
    return {
        "callable": eq.callable,
        "inputs": eq.inputs,
        "outputs": eq.outputs,
        "primary": eq.primary,
        "decls": {
            name: {
                "dim": _dim_data(decl.unit.dim),
                "unit": _unit_data(decl.unit),
                "description": describe_full(decl.unit.dim),
                "doc": decl.doc or name,
            }
            for name, decl in eq.decls.items()
        },
        "relations": [
            {"name": rel.lhs.name, "expr": _expression_data(rel.rhs)}
            for rel in eq.order
        ],
    }


def _unit_table() -> Dict[str, Dict[str, object]]:
    names = set(all_unit_names())
    for prefix in PREFIXES:
        names.update(prefix + name for name in all_unit_names())
    result = {}
    for name in names:
        unit = lookup_unit(name)
        if unit is not None:
            result[name] = {
                "dim": _dim_data(unit.dim), "scale": unit.scale, "offset": unit.offset,
            }
    return result


def render_calculator(interpreter, equation_name: str) -> str:
    """Render a calculator page, requiring declared units for its user-facing inputs."""
    eq = interpreter.equations[equation_name]
    if not eq.callable:
        raise ForgeError(f"{eq.name} does not define callable outputs", title="Calculator unavailable",
                         hint="A calculator needs an equation with output formulas.")
    if eq.primary is None:
        raise ForgeError(f"{eq.name} has no primary output", title="Calculator unavailable")
    undeclared = [name for name in eq.inputs if name not in eq.decls]
    if undeclared:
        raise ForgeError(
            f"{eq.name} needs unit declarations for calculator inputs: {', '.join(undeclared)}",
            title="Calculator unavailable",
            hint=f"Add declarations such as '{undeclared[0]} : kg' to {eq.name}.",
        )

    outputs = {}
    for name in eq.outputs:
        decl = eq.decls.get(name)
        unit = decl.unit if decl is not None else (
            Unit.from_dim(eq.inferred[name]) if name in eq.inferred else None
        )
        if unit is None:
            raise ForgeError(
                f"the unit of output '{name}' cannot be inferred",
                title="Calculator unavailable",
                hint=f"Declare its unit in {eq.name}, for example '{name} : N'.",
            )
        outputs[name] = {
            "unit": _unit_data(unit),
            "description": describe_full(unit.dim),
            "doc": (decl.doc if decl and decl.doc else name),
        }

    constants = {
        name: {"value": value.value, "dim": _dim_data(value.dim)}
        for name, value in CONSTANTS.items()
    }
    data = {
        "name": eq.name,
        "description": eq.metadata.get("description", ""),
        "equation": equation_name,
        "equations": {name: _equation_data(item) for name, item in interpreter.equations.items()},
        "inputs": eq.inputs,
        "outputs": outputs,
        "constants": constants,
        "functions": list(FUNCTIONS),
        "arities": ARITY,
        "units": _unit_table(),
    }
    payload = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

    return _HTML.replace("__DATA__", payload).replace(
        "__TITLE__", html.escape(eq.name, quote=True)
    ).replace("__DESCRIPTION__", html.escape(eq.metadata.get("description", "")))


_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ - F²ORGE Calculator</title>
<style>
:root{color-scheme:light dark;font:16px system-ui,sans-serif}
body{max-width:760px;margin:3rem auto;padding:0 1.25rem;background:Canvas;color:CanvasText}
h1{margin-bottom:.25rem} .description{color:GrayText;margin-top:0}
form{display:grid;grid-template-columns:minmax(8rem,1fr) minmax(10rem,2fr);gap:.8rem 1rem;align-items:center}
label{font-weight:600}.hint{display:block;color:GrayText;font-size:.85rem;font-weight:400}
input{font:inherit;padding:.65rem .75rem;border:1px solid GrayText;border-radius:.35rem;background:Canvas;color:CanvasText}
#error{color:#c62828;min-height:1.5rem;margin:.75rem 0}
.outputs{border-top:1px solid GrayText;margin-top:1rem;padding-top:1rem}
.result{display:flex;justify-content:space-between;gap:1rem;padding:.55rem 0}
.result output{font-variant-numeric:tabular-nums;font-weight:700}
footer{margin-top:2rem;color:GrayText;font-size:.85rem}
@media(max-width:520px){form{grid-template-columns:1fr;gap:.35rem}.hint{margin-bottom:.35rem}}
</style>
</head>
<body>
<h1 id="title"></h1><p class="description" id="description"></p>
<form id="inputs"></form><p id="error" role="alert" aria-live="polite"></p>
<section class="outputs" id="outputs" aria-live="polite"></section>
<footer>Generated by F²ORGE. This calculator runs locally in your browser and needs no internet connection.</footer>
<script>
"use strict";
const DATA = __DATA__;
const $ = (selector) => document.querySelector(selector);
const sameDim = (a,b) => a.length===b.length && a.every((x,i)=>Math.abs(x-b[i])<1e-10);
const addDim = (a,b,k=1) => a.map((x,i)=>x+k*b[i]);
const q = (value,dim,affine=false) => ({value,dim,affine});
const unitValue = (u) => ({value:u.scale,dim:u.dim,offset:u.offset||0,label:u.label||""});
function add(a,b,subtract=false){
  if(!sameDim(a.dim,b.dim)) throw Error(subtract?"Cannot subtract values with different units.":"Cannot add values with different units.");
  if(!subtract&&a.affine&&b.affine) throw Error("Cannot add two absolute temperatures.");
  return q(a.value+(subtract?-1:1)*b.value,a.dim,subtract?false:(b.affine||a.affine));
}
function evaluate(node,scope,depth=0){
  if(depth>32) throw Error("Equation calls are nested too deeply.");
  switch(node.kind){
    case "number": return q(node.value,[0,0,0,0,0,0,0]);
    case "quantity": return q(node.value*node.unit.scale+node.unit.offset,node.unit.dim,!!node.unit.offset);
    case "name":
      if(Object.hasOwn(scope,node.name)) return scope[node.name];
      if(Object.hasOwn(DATA.constants,node.name)){const c=DATA.constants[node.name];return q(c.value,c.dim);}
      throw Error("Undefined value: "+node.name);
    case "unary": {
      const a=evaluate(node.value,scope,depth);
      if(a.affine) throw Error("Cannot negate an absolute temperature.");
      return q(node.op==="-"?-a.value:a.value,a.dim,a.affine);
    }
    case "binary": {
      const a=evaluate(node.left,scope,depth),b=evaluate(node.right,scope,depth);
      if(node.op==="+") return add(a,b);
      if(node.op==="-") return add(a,b,true);
      if(node.op==="*") return q(a.value*b.value,addDim(a.dim,b.dim));
      if(node.op==="/"){if(b.value===0)throw Error("Division by zero.");return q(a.value/b.value,addDim(a.dim,b.dim,-1));}
      if(!sameDim(b.dim,[0,0,0,0,0,0,0])) throw Error("An exponent must be dimensionless.");
      const value=Math.pow(a.value,b.value);
      if(!Number.isFinite(value)) throw Error("The power result is not finite.");
      return q(value,a.dim.map(x=>x*b.value));
    }
    case "member": {
      const values=node.value.kind==="call"&&!DATA.functions.includes(node.value.name)
        ?callEquationExpression(node.value,scope,depth):evaluate(node.value,scope,depth);
      if(!values||!Object.hasOwn(values,node.name)) throw Error("Missing equation output: "+node.name);
      return values[node.name];
    }
    case "call": {
      if(DATA.functions.includes(node.name)){
        const args=node.args.map(x=>evaluate(x,scope,depth));
        return callFunction(node.name,args);
      }
      const nested=DATA.equations[node.name];
      if(!nested) throw Error("Unknown equation: "+node.name);
      const values=callEquationExpression(node,scope,depth);
      return values[nested.primary];
    }
    default: throw Error("Unsupported formula expression.");
  }
}
function callEquationExpression(node,scope,depth){
  const nested=DATA.equations[node.name];
  if(!nested)throw Error("Unknown equation: "+node.name);
  const args={};
  for(const [name,value] of Object.entries(node.kwargs))args[name]=evaluate(value,scope,depth+1);
  return callEquation(nested,args,depth+1);
}
function callFunction(name,args){
  const a=args[0],plain=[0,0,0,0,0,0,0];
  const [minimum,maximum]=DATA.arities[name];
  if(args.length<minimum||args.length>maximum)throw Error(name+"() received the wrong number of values.");
  if(name==="min"||name==="max"){
    if(args.length<2||args.some(x=>!sameDim(x.dim,a.dim)))throw Error(name+"() needs values with matching units.");
    const picked=args.reduce((best,x)=>name==="min"?(x.value<best.value?x:best):(x.value>best.value?x:best));
    return picked;
  }
  if(name==="atan2"){
    if(!sameDim(args[1].dim,a.dim))throw Error("atan2() needs values with matching units.");
    return q(Math.atan2(a.value,args[1].value),plain);
  }
  if(name==="sqrt"){
    if(a.value<0)throw Error("sqrt() needs a non-negative value.");
    return q(Math.sqrt(a.value),a.dim.map(x=>x/2));
  }
  if(!sameDim(a.dim,plain))throw Error(name+"() requires a dimensionless input.");
  if((name==="ln"||name==="log")&&a.value<=0)throw Error(name+"() needs a positive value.");
  const functions={sin:Math.sin,cos:Math.cos,tan:Math.tan,asin:Math.asin,acos:Math.acos,atan:Math.atan,
    exp:Math.exp,ln:Math.log,log:Math.log10,abs:Math.abs};
  const result=functions[name](a.value);
  if(!Number.isFinite(result))throw Error(name+"() result is not finite.");
  return q(result,plain);
}
function callEquation(equation,args,depth=0){
  if(!equation.callable)throw Error(equation.name+" defines a relationship, not callable outputs.");
  for(const name of Object.keys(args)) if(!equation.inputs.includes(name)) throw Error("Unknown input: "+name);
  for(const name of equation.inputs){
    if(!Object.hasOwn(args,name)) throw Error("Enter a value for "+name+".");
    const decl=equation.decls[name];
    if(decl&&!sameDim(args[name].dim,decl.dim))throw Error(name+" expects "+decl.description+".");
  }
  const scope={...args};
  for(const relation of equation.relations){
    const value=evaluate(relation.expr,scope,depth+1),decl=equation.decls[relation.name];
    if(decl&&!sameDim(value.dim,decl.dim))throw Error(relation.name+" has an unexpected unit.");
    scope[relation.name]=value;
  }
  return Object.fromEntries(equation.outputs.map(name=>[name,scope[name]]));
}
function parseUnit(source){
  const normalized=source.replace(/[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+/g,run=>"^"+[...run].map(c=>"0123456789-"["⁰¹²³⁴⁵⁶⁷⁸⁹⁻".indexOf(c)]).join(""));
  const tokens=normalized.match(/[A-Za-zµΩ°]+|[-+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:\\/\\d+)?|[*/^()]/g)||[];
  if(tokens.join("")!==normalized.replace(/\\s/g,""))throw Error("Invalid unit: "+source);
  let i=0;
  function primary(){
    let result;
    if(tokens[i]==="("){i++;result=expression();if(tokens[i++]!==")")throw Error("Unclosed unit parenthesis.");}
    else {const spec=DATA.units[tokens[i++]];if(!spec)throw Error("Unknown unit: "+tokens[i-1]);result={dim:spec.dim,scale:spec.scale,offset:spec.offset||0};}
    if(tokens[i]==="^"){
      i++;let exponent;
      function readExponent(){
        const token=tokens[i++];
        if(token&&token.includes("/")){const [numerator,denominator]=token.split("/").map(Number);return numerator/denominator;}
        const numerator=Number(token);
        if(tokens[i]==="/"){i++;return numerator/Number(tokens[i++]);}
        return numerator;
      }
      if(tokens[i]==="("){i++;exponent=readExponent();if(tokens[i++]!==")")throw Error("Invalid unit exponent.");}
      else exponent=readExponent();
      if(!Number.isFinite(exponent))throw Error("Invalid unit exponent.");
      result={dim:result.dim.map(x=>x*exponent),scale:Math.pow(result.scale,exponent),offset:exponent===1?result.offset:0};
    }
    return result;
  }
  function expression(){
    let result=primary();
    while(tokens[i]==="*"||tokens[i]==="/"){
      const op=tokens[i++],next=primary();
      result={dim:addDim(result.dim,next.dim,op==="*"?1:-1),scale:result.scale*(op==="*"?next.scale:1/next.scale),offset:0};
    }
    return result;
  }
  const unit=expression();
  if(i!==tokens.length)throw Error("Invalid unit: "+source);
  return unit;
}
function parseInput(text,decl,name){
  const match=text.trim().match(/^([+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?)\\s*(.*?)$/);
  if(!match)throw Error(name+" must be a number, optionally followed by a unit.");
  const magnitude=Number(match[1]);
  if(!Number.isFinite(magnitude))throw Error(name+" must be finite.");
  const unit=match[2]?parseUnit(match[2]):unitValue(decl.unit);
  if(!sameDim(unit.dim,decl.dim))throw Error(name+" expects "+decl.description+", but got "+(match[2]||"a dimensionless value")+".");
  return q(magnitude*unit.scale+unit.offset,unit.dim,!!unit.offset);
}
function numberText(value){
  if(value===0)return "0";
  return Number(value.toPrecision(10)).toString();
}
function recalculate(){
  const error=$("#error");error.textContent="";
  try{
    const args={};
    for(const name of DATA.inputs){
      const decl=DATA.equations[DATA.equation].decls[name];
      args[name]=parseInput($("#input-"+name).value,decl,name);
    }
    const values=callEquation(DATA.equations[DATA.equation],args);
    for(const [name,spec] of Object.entries(DATA.outputs)){
      const value=values[name];
      $("#result-"+name).textContent=numberText((value.value-spec.unit.offset)/spec.unit.scale)+" "+spec.unit.label;
    }
  }catch(err){error.textContent=err.message;for(const name of Object.keys(DATA.outputs))$("#result-"+name).textContent="—";}
}
$("#title").textContent=DATA.name+" calculator";
$("#description").textContent=DATA.description;
for(const name of DATA.inputs){
  const decl=DATA.equations[DATA.equation].decls[name];
  const label=document.createElement("label");label.htmlFor="input-"+name;
  label.textContent=decl.doc;
  const hint=document.createElement("span");hint.className="hint";hint.textContent=decl.description+" · "+decl.unit.label;
  label.appendChild(hint);
  const input=document.createElement("input");input.id="input-"+name;input.name=name;input.type="text";
  input.inputMode="decimal";input.autocomplete="off";input.placeholder="e.g. 150 "+decl.unit.label;input.value="";
  input.addEventListener("input",recalculate);
  $("#inputs").append(label,input);
}
for(const [name,spec] of Object.entries(DATA.outputs)){
  const row=document.createElement("div");row.className="result";
  const label=document.createElement("span");label.textContent=spec.doc+" ("+spec.unit.label+")";
  const value=document.createElement("output");value.id="result-"+name;value.textContent="—";
  row.append(label,value);$("#outputs").appendChild(row);
}
</script>
</body>
</html>
"""
