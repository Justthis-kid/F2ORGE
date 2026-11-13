"""Signal processing: the discrete Fourier transform, filtering, and frequency-response data.

Everything here works on plain vectors, so a signal is a column of samples and a spectrum is a
vector of complex amplitudes.  The transforms are iterative radix-2, with a direct sum for lengths
that are not a power of two, so no dependency is needed and results are correct for any length.

    t = linspace(0 s, 1 s, 1000)                       # 1 kHz sampling
    y = sin(2 * pi * 50 Hz * t) + 0.5 * sin(2 * pi * 120 Hz * t)
    spectrum = fft(y)
    freqs = fftfreq(count(y), 1 ms)
    mag(spectrum[2])                                   # the amplitude of the 50 Hz line

    clean = lowpass(y, 80 Hz, 1 ms)                    # drop the 120 Hz component
    [gain, phase] = bode_response(R, C, 1 Hz .. 100 kHz)
"""
from __future__ import annotations

import cmath
import math
from typing import List, Sequence, Tuple

from .errors import ForgeEvalError, UnitError
from .linear_algebra import Vector
from .quantity import Quantity
from .units import Unit


def _complex_list(values: Sequence[complex]) -> List[complex]:
    return [complex(value) for value in values]


def dft(values: Sequence[complex]) -> List[complex]:
    """The discrete Fourier transform, by a direct sum.  Exact but O(n²); used for odd lengths."""
    n = len(values)
    twiddles = [cmath.exp(-2j * math.pi * k / n) for k in range(n)]
    out: List[complex] = []
    for k in range(n):
        total = 0j
        step = k
        for index in range(n):
            total += values[index] * twiddles[(step * index) % n]
        out.append(total)
    return out


def fft(values: Sequence[complex]) -> List[complex]:
    """The discrete Fourier transform: radix-2 when the length is a power of two."""
    data = _complex_list(values)
    n = len(data)
    if n == 0:
        return []
    if n & (n - 1):  # not a power of two
        return dft(data)
    # Bit-reversal permutation, then butterfly stages.
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            data[i], data[j] = data[j], data[i]
    size = 2
    while size <= n:
        angle = -2j * math.pi / size
        half = size // 2
        twiddle = [cmath.exp(angle * k) for k in range(half)]
        for start in range(0, n, size):
            for k in range(half):
                even = data[start + k]
                odd = data[start + k + half] * twiddle[k]
                data[start + k] = even + odd
                data[start + k + half] = even - odd
        size *= 2
    return data


def ifft(values: Sequence[complex]) -> List[complex]:
    """The inverse transform, normalised so that ifft(fft(y)) is y."""
    n = len(values)
    if n == 0:
        return []
    transformed = fft([value.conjugate() for value in values])
    return [value.conjugate() / n for value in transformed]


def frequencies(count: int, spacing: Quantity) -> List[Quantity]:
    """The frequency of each bin of an fft: 0, 1/T, 2/T, ... up to just below the sample rate."""
    if spacing.value is None or spacing.value == 0:
        raise ForgeEvalError("the sample spacing must not be zero")
    step = 1.0 / (spacing.value * count)
    dim = Unit.from_atoms([("Hz", 1)]).dim if spacing.dim.is_dimensionless else spacing.dim ** -1
    unit = Unit.from_dim(dim)
    return [Quantity(k * step, dim, unit) for k in range(count)]


def magnitudes(values: Sequence[complex]) -> List[float]:
    return [abs(complex(value)) for value in values]


def phases(values: Sequence[complex]) -> List[float]:
    return [cmath.phase(complex(value)) for value in values]


def window(values: Sequence[float], kind: str) -> List[float]:
    """Apply a window before transforming: `hann` reduces leakage of a tone across bins."""
    n = len(values)
    if kind in ("none", "rectangular"):
        return list(values)
    if n == 1:
        return list(values)
    if kind == "hann":
        weights = [0.5 - 0.5 * math.cos(2 * math.pi * k / (n - 1)) for k in range(n)]
    elif kind == "hamming":
        weights = [0.54 - 0.46 * math.cos(2 * math.pi * k / (n - 1)) for k in range(n)]
    elif kind == "blackman":
        weights = [0.42 - 0.5 * math.cos(2 * math.pi * k / (n - 1))
                   + 0.08 * math.cos(4 * math.pi * k / (n - 1)) for k in range(n)]
    else:
        raise ForgeEvalError(f"'{kind}' is not a window; use \"hann\", \"hamming\", or \"blackman\"")
    return [value * weight for value, weight in zip(values, weights)]


def convolve(values: Sequence[float], taps: Sequence[float]) -> List[float]:
    """A finite impulse response: each output is the weighted sum of recent inputs."""
    if not taps:
        raise ForgeEvalError("a filter needs at least one coefficient")
    n, m = len(values), len(taps)
    out: List[float] = []
    for index in range(n):
        total = 0.0
        for k, tap in enumerate(taps):
            if index - k >= 0:
                total += tap * values[index - k]
        out.append(total)
    return out


def lowpass_taps(cutoff_hz: float, sample_hz: float, length: int = 101) -> List[float]:
    """A windowed-sinc low-pass kernel, normalised to unity gain at zero frequency."""
    nyquist = sample_hz / 2.0
    if cutoff_hz <= 0 or cutoff_hz >= nyquist:
        raise ForgeEvalError(
            f"the cutoff must lie between 0 and the Nyquist frequency ({nyquist:g} Hz)")
    half = length // 2
    taps: List[float] = []
    for k in range(length):
        n = k - half
        ratio = cutoff_hz / sample_hz
        value = 2 * ratio if n == 0 else math.sin(2 * math.pi * ratio * n) / (math.pi * n)
        # A Hamming taper stops the kernel from ringing into neighbouring frequencies.
        taps.append(value * (0.54 - 0.46 * math.cos(2 * math.pi * k / (length - 1))))
    total = sum(taps)
    return [tap / total for tap in taps]


def highpass_taps(cutoff_hz: float, sample_hz: float, length: int = 101) -> List[float]:
    """The complement of a low-pass kernel: unity at high frequencies, zero at zero frequency."""
    low = lowpass_taps(cutoff_hz, sample_hz, length)
    half = length // 2
    return [-tap if index != half else 1.0 - tap for index, tap in enumerate(low)]


def bandpass_taps(low_hz: float, high_hz: float, sample_hz: float, length: int = 101) -> List[float]:
    """A band-pass kernel from the difference of two low-pass kernels."""
    low = lowpass_taps(high_hz, sample_hz, length)
    upper = lowpass_taps(low_hz, sample_hz, length)
    return [a - b for a, b in zip(low, upper)]


def response(taps: Sequence[float], frequency_hz: float, sample_hz: float) -> complex:
    """The complex gain of an FIR filter at one frequency: z^-1 = e^{-j w}."""
    omega = 2 * math.pi * frequency_hz / sample_hz
    return sum(tap * cmath.exp(-1j * omega * k) for k, tap in enumerate(taps))


def first_order_response(cutoff_hz: float, frequencies_hz: Sequence[float]) -> List[Tuple[float, float]]:
    """Gain and phase of a first-order low-pass H(s) = 1 / (1 + s/wc), for a Bode plot."""
    pairs: List[Tuple[float, float]] = []
    for frequency in frequencies_hz:
        if frequency <= 0:
            raise ForgeEvalError("a Bode plot needs positive frequencies")
        ratio = frequency / cutoff_hz
        gain = 1.0 / math.sqrt(1.0 + ratio * ratio)
        phase = -math.degrees(math.atan(ratio))
        pairs.append((gain, phase))
    return pairs


def second_order_response(cutoff_hz: float, damping: float,
                          frequencies_hz: Sequence[float]) -> List[Tuple[float, float]]:
    """Gain and phase of a second-order low-pass with a damping ratio, for a resonance peak."""
    pairs: List[Tuple[float, float]] = []
    for frequency in frequencies_hz:
        if frequency <= 0:
            raise ForgeEvalError("a Bode plot needs positive frequencies")
        ratio = frequency / cutoff_hz
        real = 1.0 - ratio * ratio
        imag = 2.0 * damping * ratio
        pairs.append((1.0 / math.hypot(real, imag), -math.degrees(math.atan2(imag, real))))
    return pairs
