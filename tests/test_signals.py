"""Signal processing: fft(), filtering, and frequency-response data."""
import pytest

from f2orge.errors import ForgeEvalError
from helpers import error_of, run

TONE = """n = 64
t = linspace(0 s, 1 s, 64)
y = sin(2 * pi * 8 Hz * t)
s = fft(y)
f = fftfreq(64, 1 s / 64)
"""


def test_fft_finds_the_frequency_of_a_tone():
    assert run(TONE + "f[8]") == ["8 Hz"]
    assert float(run(TONE + "mag(s[8])")[0]) > 30


def test_fft_round_trips_through_ifft():
    out = run("y = <1, 2, 3, 4>\nback = ifft(fft(y))\nback[1]")
    assert abs(float(out[0].split()[0]) - 2) < 1e-12


def test_fftfreq_reports_one_bin_per_sample_divided_by_the_record():
    out = run("f = fftfreq(4, 1 s)\nf[0]\nf[1]\nf[3]")
    assert out == ["0 Hz", "0.25 Hz", "0.75 Hz"]


def test_spectrum_windows_and_transforms_in_one_step():
    out = run("y = <1, 0, -1, 0>\n[s, f] = spectrum(y, 1 s)\ncount(f)\ncount(s)")
    assert out == ["4", "4"]


def test_lowpass_removes_a_high_tone():
    src = """n = 200
t = linspace(0 s, 199 ms, 200)
y = sin(2 * pi * 5 Hz * t) + sin(2 * pi * 100 Hz * t)
clean = lowpass(y, 20 Hz, 1 ms)
sum(clean .* clean)
sum(y .* y)"""
    clean, original = [float(value) for value in run(src)]
    assert clean < 0.4 * original  # most of the 100 Hz energy is gone


def test_highpass_and_bandpass_build_from_the_same_kernel():
    # Samples 10 ms apart have a Nyquist frequency of 50 Hz, so these cutoffs are in range.
    assert run("count(highpass(<1, 2, 3, 2, 1>, 10 Hz, 10 ms))") == ["5"]
    assert run("count(bandpass(<1, 2, 3, 2, 1>, 10 Hz, 20 Hz, 10 ms))") == ["5"]


def test_windows_taper_a_signal():
    assert run('window(<1, 1, 1>, "hann")') == ["<0, 1, 0>"]
    assert run('window(<1, 1, 1>, "none")') == ["<1, 1, 1>"]
    assert "hann" in error_of('window(<1, 1>, "kaiser")').message


def test_first_order_bode_is_minus_three_decibels_at_the_cutoff():
    out = run("f = <100 Hz>\n[gain, phase] = bode(f, 100 Hz)\ngain[0]\nphase[0]")
    assert abs(float(out[0]) - 0.7071067812) < 1e-9
    assert out[1] == "-45 deg"


def test_second_order_resonance_peaks_by_the_quality_factor():
    out = run("f = <100 Hz>\n[g, p] = resonance(f, 0.1, 100 Hz)\ng[0]")
    assert abs(float(out[0]) - 5.0) < 1e-9


def test_element_wise_functions_and_powers_of_a_vector():
    assert run("sqrt(<1, 4, 9>)") == ["<1, 2, 3>"]
    assert run("<1, 2, 3>^2") == ["<1, 4, 9>"]
    assert run("<1, 2> .* <3, 4>") == ["<3, 8>"]


@pytest.mark.parametrize("src", [
    "fft(<>)",
    "fftfreq(4, 0 s)",
    "lowpass(<1, 2, 3>, 0 Hz, 1 ms)",
])
def test_signal_errors(src):
    assert isinstance(error_of(src), ForgeEvalError)
