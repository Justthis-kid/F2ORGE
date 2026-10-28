# F²ORGE language support for VS Code

Syntax highlighting for `.forge` programs and `.eq` equation files: keywords, equation names,
declarations (`m : kg`), numbers with their units (`9.81 m/s²`), functions, constants, comments.

## Install (PowerShell)

Copy the folder into your VS Code extensions directory, then run "Developer: Reload Window":

```powershell
Copy-Item -Recurse -Force vscode-forge "$env:USERPROFILE\.vscode\extensions\f2orge.forge-language-0.1.0"
```

macOS / Linux:

```bash
cp -R vscode-forge ~/.vscode/extensions/f2orge.forge-language-0.1.0
```

Or build a .vsix: `npx @vscode/vsce package` inside this folder, then
`code --install-extension forge-language-0.1.0.vsix`.
