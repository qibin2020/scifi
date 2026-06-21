// v3 binder — thin config over the generic AXIS-like stream binder (general/harness/stream_binder.hh).
// V3 complex: N_PATCHES windows + (CONV2_WINDOW-1) PAD flush / sample, N_PATCHES signed outs/sample.
// Constants patched per-model by assemble_wrap.py from convert_meta.json.
#include "Vstream_wrapper.h"
#include "stream_binder.hh"

struct cfg {
    static constexpr size_t CHUNK          = 25;   // patch size
    static constexpr size_t BW_INP         = 10;   // ADC bits
    static constexpr size_t WINDOWS        = 20;   // N_PATCHES
    static constexpr size_t N_FLUSH        = 2;    // CONV2_WINDOW-1 trailing PAD windows
    static constexpr size_t OUT_PER_SAMPLE = 20;   // per-patch outputs
    static constexpr size_t BW_OUT         = 15;   // oq width (model-specific)
    static constexpr bool   SIGNED_OUT     = true;
    typedef Vstream_wrapper dut_t;
};

extern "C" size_t inference(const int32_t *c_inp, int32_t *c_out, size_t n_samples,
                            double inp_pause_prob, uint32_t seed) {
    return stream_inference<cfg>(c_inp, c_out, n_samples, inp_pause_prob, seed);
}
