"""
v3_ref assemble_wrap — build wrap_pkg/sim from converted cores + hand wrapper + shared general harness.

  wrap/                 case-by-case top:  stream_wrapper.v + stream_wrapper_binder.cc (thin cfg)
  ../general/harness/   shared driver:     verify_golden.py, build_binder.mk, ioutil.hh,
                                           stream_binder.hh, static/*.v
  rtl_kernel/src/static/{scale_lut,bias_lut}.mem   per-patch tail LUTs
  convert_meta.json     derived widths (width-adaptive)
"""
import json, re, shutil
from pathlib import Path

HERE    = Path(__file__).resolve().parent
WRAP    = HERE / 'wrap'
HARNESS = HERE.parent / 'general' / 'harness'
meta = json.load(open(HERE / 'convert_meta.json'))
W = meta['CONV2_WINDOW']

WRAP_PARAMS = {
    'KERNEL_INPUT_BIT':  meta['kernel_input_bits'], 'KERNEL_OUTPUT_BIT': meta['kernel_pad_bits'],
    'MID_INPUT_BIT':     meta['mid_input_pad_bits'], 'MID_OUTPUT_BIT':    meta['mid_output_pad_bits'],
    'N_PATCHES': meta['N_PATCHES'], 'CONV2_WINDOW': W, 'N_FLUSH': W-1, 'ACCUM_START': W-1,
    'REQ_SHIFT': meta['REQ_SHIFT'], 'Q_BITS': meta['Q_BITS'],
    'PROD_SHIFT': meta['PROD_SHIFT'], 'SCALE_SIGNED': meta['SCALE_SIGNED'],
    'SCALE_BITS': meta['SCALE_BITS'], 'BIAS_BITS': meta['BIAS_BITS'], 'OUT_BITS': meta['OUT_BITS'],
    'OUT_MIN': meta['OUT_MIN'], 'OUT_MAX': meta['OUT_MAX'],
}
BINDER_CONSTS = {'CHUNK': meta['PATCH_SIZE'], 'BW_INP': meta['BW_INP'], 'WINDOWS': meta['N_PATCHES'],
                 'N_FLUSH': W-1, 'OUT_PER_SAMPLE': meta['N_PATCHES'], 'BW_OUT': meta['OUT_BITS']}
print('derived:', {k: WRAP_PARAMS[k] for k in ('KERNEL_OUTPUT_BIT','MID_OUTPUT_BIT','REQ_SHIFT','Q_BITS','OUT_BITS')})

sim = HERE / 'wrap_pkg' / 'sim'; src = sim / 'src'
if sim.exists(): shutil.rmtree(sim)
(src / 'static').mkdir(parents=True)

for core in ('rtl_kernel', 'rtl_mid'):
    csrc = HERE / core / 'src'
    for f in csrc.glob('*.v'): shutil.copy(f, src / f.name)
    for f in (csrc / 'static').glob('*.v'): shutil.copy(f, src / 'static' / f.name)
for f in (HARNESS / 'static').glob('*.v'):
    if not (src / 'static' / f.name).exists(): shutil.copy(f, src / 'static' / f.name)
for need in ('lookup_table.v', 'multiplier.v'):
    assert (src / 'static' / need).exists(), f'missing {need}'
for mem in ('scale_lut.mem', 'bias_lut.mem'):
    msrc = HERE / 'rtl_kernel' / 'src' / 'static' / mem
    assert msrc.exists(), f'{mem} missing — run convert.py'
    shutil.copy(msrc, src / 'static' / mem); shutil.copy(msrc, sim / mem)

wtxt = (WRAP / 'stream_wrapper.v').read_text()
def setp(t, n, v):
    nt, c = re.subn(rf'(parameter integer {n}\s*=\s*)-?\d+', rf'\g<1>{v}', t); assert c == 1, f'param {n}: {c}'; return nt
for n, v in WRAP_PARAMS.items(): wtxt = setp(wtxt, n, v)
(src / 'stream_wrapper.v').write_text(wtxt)

btxt = (WRAP / 'stream_wrapper_binder.cc').read_text()
def setc(t, n, v):
    nt, c = re.subn(rf'(static constexpr size_t {n}\s*=\s*)\d+', rf'\g<1>{v}', t); assert c == 1, f'cfg {n}: {c}'; return nt
for n, v in BINDER_CONSTS.items(): btxt = setc(btxt, n, v)
(sim / 'stream_wrapper_binder.cc').write_text(btxt)

for f in ('verify_golden.py', 'build_binder.mk', 'ioutil.hh', 'stream_binder.hh'):
    shutil.copy(HARNESS / f, sim / f)
golden = HERE / 'golden'
assert (golden / 'golden_X.csv').exists(), 'run ../common/gen_golden.py first'
(sim.parent / 'dataset').mkdir(parents=True, exist_ok=True)
shutil.copy(golden / 'golden_X.csv', sim.parent / 'dataset' / 'golden_X.csv')
shutil.copy(golden / 'golden_Y.csv', sim.parent / 'dataset' / 'golden_Y.csv')
print('assembled wrap_pkg/sim. Now: cd wrap_pkg/sim && python3 verify_golden.py --no-pause')
