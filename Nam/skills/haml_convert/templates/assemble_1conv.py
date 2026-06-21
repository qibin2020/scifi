"""
v1_ref assemble_wrap — build wrap_pkg/sim from converted cores + hand wrapper + shared general harness.

  wrap/                 case-by-case top:  stream_wrapper.v + stream_wrapper_binder.cc (thin cfg)
  ../general/harness/   shared driver:     verify_golden.py, build_binder.mk, ioutil.hh,
                                           stream_binder.hh, static/*.v
  convert_meta.json     derived widths (width-adaptive; nothing hardcoded)
"""
import json, re, shutil
from pathlib import Path

HERE    = Path(__file__).resolve().parent
WRAP    = HERE / 'wrap'
HARNESS = HERE.parent / 'general' / 'harness'
BW_INP  = 10

meta = json.load(open(HERE / 'convert_meta.json'))
CHUNK, II = meta['break_input'], meta['break_n']
KOB, DENSE = meta['kernel_pad_bits'], meta['dense_pad_bits']
INPUT_ACTUAL, OUTPUT_ACTUAL = CHUNK * BW_INP, meta['output_bw_total']
assert DENSE == II * KOB, f'{II}*{KOB} != {DENSE}'
print(f'derived: CHUNK={CHUNK} II={II} KERNEL_OUTPUT_BIT={KOB} OUTPUT_ACTUAL={OUTPUT_ACTUAL}')

sim = HERE / 'wrap_pkg' / 'sim'; src = sim / 'src'
if sim.exists(): shutil.rmtree(sim)
(src / 'static').mkdir(parents=True)

for core in ('rtl_kernel', 'rtl_dense'):
    csrc = HERE / core / 'src'
    for f in csrc.glob('*.v'): shutil.copy(f, src / f.name)
    for f in (csrc / 'static').glob('*.v'): shutil.copy(f, src / 'static' / f.name)
for f in (HARNESS / 'static').glob('*.v'):
    if not (src / 'static' / f.name).exists(): shutil.copy(f, src / 'static' / f.name)

# stream_wrapper.v param patch
Wtxt = (WRAP / 'stream_wrapper.v').read_text()
def setp(t, n, v):
    nt, c = re.subn(rf'(parameter integer {n}\s*=\s*)-?\d+', rf'\g<1>{v}', t); assert c == 1, f'param {n}: {c}'; return nt
for n, v in (('INPUT_ACTUAL', INPUT_ACTUAL), ('KERNEL_OUTPUT_BIT', KOB), ('II', II), ('OUTPUT_ACTUAL', OUTPUT_ACTUAL)):
    Wtxt = setp(Wtxt, n, v)
(src / 'stream_wrapper.v').write_text(Wtxt)

# binder cfg patch (thin config over the generic stream_binder)
B = (WRAP / 'stream_wrapper_binder.cc').read_text()
def setc(t, n, v):
    nt, c = re.subn(rf'(static constexpr size_t {n}\s*=\s*)\d+', rf'\g<1>{v}', t); assert c == 1, f'cfg {n}: {c}'; return nt
for n, v in (('CHUNK', CHUNK), ('BW_INP', BW_INP), ('WINDOWS', II), ('N_FLUSH', 0),
             ('OUT_PER_SAMPLE', 1), ('BW_OUT', OUTPUT_ACTUAL)):
    B = setc(B, n, v)
(sim / 'stream_wrapper_binder.cc').write_text(B)

# shared general harness + golden
for f in ('verify_golden.py', 'build_binder.mk', 'ioutil.hh', 'stream_binder.hh'):
    shutil.copy(HARNESS / f, sim / f)
golden = HERE / 'golden'
assert (golden / 'golden_X.csv').exists(), 'run ../common/gen_golden.py first'
(sim.parent / 'dataset').mkdir(parents=True, exist_ok=True)
shutil.copy(golden / 'golden_X.csv', sim.parent / 'dataset' / 'golden_X.csv')
shutil.copy(golden / 'golden_Y.csv', sim.parent / 'dataset' / 'golden_Y.csv')
print('assembled wrap_pkg/sim. Now: cd wrap_pkg/sim && python3 verify_golden.py --no-pause')
