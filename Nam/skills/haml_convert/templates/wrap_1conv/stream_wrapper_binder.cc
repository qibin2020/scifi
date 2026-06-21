// v1 binder — thin config over the generic AXIS-like stream binder (general/harness/stream_binder.hh).
// V1 simple: II=20 windows/sample, no flush, 1 scalar out/sample, unsigned. Constants patched
// per-model by assemble_wrap.py from convert_meta.json.
#include "Vstream_wrapper.h"
#include "stream_binder.hh"

struct cfg {
    static constexpr size_t CHUNK          = 25;   // kernel_size
    static constexpr size_t BW_INP         = 10;   // ADC bits
    static constexpr size_t WINDOWS        = 20;   // II = waveform_len / kernel_size
    static constexpr size_t N_FLUSH        = 0;    // no padding boundary
    static constexpr size_t OUT_PER_SAMPLE = 1;    // scalar output
    static constexpr size_t BW_OUT         = 28;   // dense output width (model-specific)
    static constexpr bool   SIGNED_OUT     = false;
    typedef Vstream_wrapper dut_t;
};

extern "C" size_t inference(const int32_t *c_inp, int32_t *c_out, size_t n_samples,
                            double inp_pause_prob, uint32_t seed) {
    return stream_inference<cfg>(c_inp, c_out, n_samples, inp_pause_prob, seed);
}
