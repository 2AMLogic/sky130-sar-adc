"""Stdlib-only coherent-sampling FFT / SNDR / ENOB analyzer (issue #603).

Turns a captured ADC output-code stream (one integer code per conversion)
into the standard dynamic-test figures -- SNDR, ENOB, SFDR -- by a radix-2
FFT. Pure Python on purpose: `sim/` runs without a venv (see
`sim/README.md`), so numpy is not available to the harness and is not
assumed here.

METHOD (`sim/README.md` "Dynamic-test (FFT) metadata"):

  * Coherent sampling, no window. The input tone sits exactly on FFT bin
    `tone_bin` of an `N`-point record (`f_in = tone_bin * f_s / N`), with
    `N` a power of two and `tone_bin` coprime to `N`, so the record holds an
    integer number of input cycles, every sample lands on a distinct input
    phase, and the tone's energy falls entirely in one bin -- no leakage, so
    no window is needed (or wanted: a window would smear the tone into its
    neighbours and the noise sum would have to exclude them).
  * Single-sided power spectrum over bins `0..N/2`. Bin 0 (DC: the
    converter's mid-scale offset plus any static offset error) is excluded
    from both signal and noise. The signal is bin `tone_bin`; noise-plus-
    distortion is every other bin `1..N/2`.
  * `SNDR = 10*log10(P_signal / P_noise+distortion)`,
    `ENOB = (SNDR - 1.76 dB) / 6.02 dB` -- the same `SNR = 6.02*ENOB + 1.76`
    relationship `sim/enob-estimate/run_enob.py` and
    `spec/dr-003-support/calc.py` use, so the two ENOB figures are on one
    scale.
  * ENOB is reported twice: at the tone's own amplitude, and normalised to a
    full-scale sine (`SNDR_FS = SNDR + 20*log10(A_FS / A)`). The normalised
    figure assumes the noise floor does not depend on amplitude -- true of
    quantization and thermal noise, NOT of amplitude-dependent distortion --
    so it is labelled as an extrapolation wherever it is used.

`ideal_quantized_sine()` generates the code stream an ideal N-bit quantizer
would produce for the same record, which a caller reports alongside a
measured result: on a short record the ideal quantizer's own SNDR estimate
is itself noisy, so the useful comparison is measured-vs-ideal at identical
`N`, bin, amplitude and phase, not measured-vs-the-textbook `6.02*N + 1.76`.
"""

from __future__ import annotations

import cmath
import math

ENOB_DB_PER_BIT = 6.02
ENOB_DB_OFFSET = 1.76


def is_power_of_two(n: int) -> bool:
    return isinstance(n, int) and n > 0 and (n & (n - 1)) == 0


def check_coherent(n: int, tone_bin: int) -> None:
    """Raise ValueError unless (`n`, `tone_bin`) is a valid coherent plan:
    `n` a power of two >= 8, `0 < tone_bin < n/2`, `gcd(tone_bin, n) == 1`."""
    if not is_power_of_two(n) or n < 8:
        raise ValueError(f"record length N={n} must be a power of two >= 8")
    if not 0 < tone_bin < n // 2:
        raise ValueError(f"tone bin {tone_bin} must lie strictly between 0 and N/2={n // 2}")
    if math.gcd(tone_bin, n) != 1:
        raise ValueError(
            f"tone bin {tone_bin} is not coprime to N={n}: the record would revisit "
            "the same input phases and not exercise N distinct codes"
        )


def fft(x: list[complex | float]) -> list[complex]:
    """Iterative radix-2 decimation-in-time FFT, `X[k] = sum x[n] e^{-j2pi kn/N}`
    (no normalisation). `len(x)` must be a power of two."""
    n = len(x)
    if not is_power_of_two(n):
        raise ValueError(f"FFT length {n} is not a power of two")
    a = [complex(v) for v in x]
    # Bit-reversal permutation.
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            a[i], a[j] = a[j], a[i]
    size = 2
    while size <= n:
        half = size // 2
        w_step = cmath.exp(-2j * math.pi / size)
        for start in range(0, n, size):
            w = 1 + 0j
            for k in range(half):
                u = a[start + k]
                v = a[start + k + half] * w
                a[start + k] = u + v
                a[start + k + half] = u - v
                w *= w_step
        size *= 2
    return a


def power_spectrum(samples: list[float]) -> list[float]:
    """Single-sided power spectrum, bins `0..N/2`, scaled so a sine of peak
    amplitude `A` on an interior bin reads `A**2 / 2` (its mean-square value)
    and the bins sum to the record's mean-square value (Parseval)."""
    n = len(samples)
    spec = fft(samples)
    out = []
    for k in range(n // 2 + 1):
        p = abs(spec[k]) ** 2 / n**2
        if 0 < k < n // 2:
            p *= 2.0  # fold the mirror-image negative-frequency bin in
        out.append(p)
    return out


def analyze(
    codes: list[int | float],
    tone_bin: int,
    n_bits: int,
) -> dict:
    """SNDR/ENOB/SFDR of a coherently-sampled code stream.

    Raises ValueError for an invalid coherent plan or a stream containing a
    missing (None) or non-finite code -- one missing conversion invalidates a
    coherent record, so it is never silently dropped or zero-filled.

    Returns a dict: `n`, `tone_bin`, `signal_power`, `noise_power`
    (noise + distortion, DC excluded), `sndr_db`, `enob_bit`,
    `amplitude_codes` (peak, from the tone bin), `full_scale_amplitude_codes`
    (`2**(n_bits-1)`), `amplitude_dbfs`, `sndr_fs_db` / `enob_fs_bit`
    (normalised to a full-scale sine -- see the module docstring's caveat),
    `peak_bin` (largest non-DC bin; equals `tone_bin` for a sane capture),
    `sfdr_db` / `spur_bin` (largest non-DC, non-tone bin), `dc_codes`,
    `n_at_rails` (codes pinned at 0 or `2**n_bits - 1`: clipping), and
    `spectrum` (the single-sided power spectrum itself)."""
    n = len(codes)
    check_coherent(n, tone_bin)
    vals: list[float] = []
    for i, c in enumerate(codes):
        if c is None or not math.isfinite(float(c)):
            raise ValueError(f"code stream sample {i} is missing or non-finite ({c!r})")
        vals.append(float(c))

    spec = power_spectrum(vals)
    signal = spec[tone_bin]
    noise = sum(p for k, p in enumerate(spec) if k not in (0, tone_bin))
    if signal <= 0.0:
        raise ValueError("no signal power in the tone bin")
    # A perfect (noise-free) stream would give infinite SNDR; floor the noise
    # at the double-precision round-off of the signal so callers get a finite,
    # obviously-ideal number instead of a ZeroDivisionError.
    noise_floor = max(noise, signal * 1e-30)
    sndr_db = 10.0 * math.log10(signal / noise_floor)
    amplitude = math.sqrt(2.0 * signal)
    fs_amp = float(2 ** (n_bits - 1))
    amplitude_dbfs = 20.0 * math.log10(amplitude / fs_amp)
    sndr_fs_db = sndr_db - amplitude_dbfs

    non_dc = list(range(1, n // 2 + 1))
    peak_bin = max(non_dc, key=lambda k: spec[k])
    spurs = [k for k in non_dc if k != tone_bin]
    spur_bin = max(spurs, key=lambda k: spec[k])
    spur = max(spec[spur_bin], signal * 1e-30)
    top = 2**n_bits - 1

    return dict(
        n=n,
        tone_bin=tone_bin,
        signal_power=signal,
        noise_power=noise,
        sndr_db=sndr_db,
        enob_bit=enob_from_sndr(sndr_db),
        amplitude_codes=amplitude,
        full_scale_amplitude_codes=fs_amp,
        amplitude_dbfs=amplitude_dbfs,
        sndr_fs_db=sndr_fs_db,
        enob_fs_bit=enob_from_sndr(sndr_fs_db),
        peak_bin=peak_bin,
        spur_bin=spur_bin,
        sfdr_db=10.0 * math.log10(signal / spur),
        dc_codes=math.sqrt(spec[0]),
        n_at_rails=sum(1 for v in vals if v <= 0 or v >= top),
        spectrum=spec,
    )


def enob_from_sndr(sndr_db: float) -> float:
    return (sndr_db - ENOB_DB_OFFSET) / ENOB_DB_PER_BIT


def sine_samples(
    n: int, tone_bin: int, amplitude: float, phase_rad: float = 0.0, offset: float = 0.0
) -> list[float]:
    """`offset + amplitude * sin(2*pi*tone_bin*i/N + phase_rad)`, i = 0..N-1:
    the continuous-valued input a coherent record samples."""
    return [
        offset + amplitude * math.sin(2.0 * math.pi * tone_bin * i / n + phase_rad)
        for i in range(n)
    ]


def ideal_quantize(value_codes: float, n_bits: int) -> int:
    """Ideal mid-tread offset-binary quantizer on a code-unit input scale
    (mid-scale = `2**(n_bits-1)`): round half up, clamp to the code range.
    (`gen_full_conversion_tb.ideal_code()` uses Python's `round()`; the two
    differ only on an exact half-code tie, which a sine sample essentially
    never lands on.)"""
    return max(0, min(2**n_bits - 1, int(math.floor(value_codes + 0.5))))


def ideal_quantized_sine(
    n: int, tone_bin: int, amplitude_fraction: float, n_bits: int, phase_rad: float = 0.0
) -> list[int]:
    """Code stream of an ideal `n_bits` quantizer sampling a sine of peak
    amplitude `amplitude_fraction` of full scale (full scale = `2**(n_bits-1)`
    codes peak, centred on mid-scale), on the coherent plan (`n`, `tone_bin`)
    with initial phase `phase_rad`."""
    half = 2 ** (n_bits - 1)
    return [
        ideal_quantize(v, n_bits)
        for v in sine_samples(n, tone_bin, amplitude_fraction * half, phase_rad, float(half))
    ]
