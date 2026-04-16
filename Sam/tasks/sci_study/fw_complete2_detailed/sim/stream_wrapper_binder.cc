#include <verilated.h>
#include "Vstream_wrapper.h"
#include "ioutil.hh"
#include <cstdint>
#include <cstddef>
#include <memory>
#include <random>
#include <algorithm>

// #define DEBUG
#ifdef DEBUG
  #define DBG(...) fprintf(stderr, __VA_ARGS__)
#else
  #define DBG(...) do {} while(0)
#endif

static constexpr size_t CHUNK  = 25;   // values per clock (500/20)
static constexpr size_t BW_INP = 10;   // bits per input value
static constexpr size_t BW_OUT = 14;   // bits per output value
static constexpr size_t II     = 20;   // initiation interval

extern "C" {

/**
 * Stream n_samples through stream_wrapper with random inp_valid pauses.
 *
 * c_inp:           flat int32 array, n_samples * 500 values
 * c_out:           output buffer (caller allocates >= n_samples entries)
 * n_samples:       total number of 500-value waveforms to stream
 * inp_pause_prob:  probability [0,1) of deasserting inp_valid each cycle
 * seed:            RNG seed for reproducible pauses
 *
 * Returns: number of outputs collected.
 */
size_t inference(const int32_t *c_inp, int32_t *c_out, size_t n_samples,
                 double inp_pause_prob, uint32_t seed) {

    auto dut = std::make_unique<Vstream_wrapper>();
    std::mt19937 rng(seed);
    std::uniform_real_distribution<double> dist(0.0, 1.0);

    dut->clk = 1;
    dut->inp_valid = 0;
    // zero out model_inp
    for (size_t i = 0; i < sizeof(dut->model_inp)/4; i++)
        dut->model_inp[i] = 0;

    size_t total_chunks = n_samples * II;
    size_t chunk_idx = 0;
    size_t n_out = 0;

    // generous cycle budget
    size_t max_cycles = (size_t)((double)total_chunks /
                        std::max(1.0 - inp_pause_prob, 0.05)) * 2 + 200;

    for (size_t cyc = 0; cyc < max_cycles; cyc++) {

        // drive input
        if (chunk_idx < total_chunks) {
            bool pause = (inp_pause_prob > 0.0 && dist(rng) < inp_pause_prob);
            if (!pause) {
                write_input<CHUNK, BW_INP>(
                    dut->model_inp, &c_inp[CHUNK * chunk_idx]
                );
                dut->inp_valid = 1;
                DBG("cyc %4zu: inp chunk %zu/%zu\n", cyc, chunk_idx, total_chunks);
                chunk_idx++;
            } else {
                dut->inp_valid = 0;
            }
        } else {
            dut->inp_valid = 0;
        }

        // clock edge
        dut->clk = 0;
        dut->eval();
        dut->clk = 1;
        dut->eval();

        // capture output
        if (dut->out_valid == 1 && n_out < n_samples) {
            read_output<1, BW_OUT>(dut->model_out, &c_out[n_out]);
            DBG("cyc %4zu: out[%zu] = %d (0x%x)\n", cyc, n_out, c_out[n_out], c_out[n_out]);
            n_out++;
        }

        // early exit
        if (chunk_idx >= total_chunks && n_out >= n_samples)
            break;
    }

    dut->final();
    return n_out;
}

} // extern "C"
