// stream_binder.hh — GENERIC AXIS-like streaming driver for a verilated stream_wrapper.
//
// Emulates an AXI-Stream feed into the `model_inp` bus with optional backpressure (input pause),
// and captures `model_out` on every `out_valid` pulse. One templated function serves every
// topology; a package's binder.cc only declares a CFG struct and calls stream_inference<CFG>.
//
//   per sample: feed CFG::WINDOWS real windows (CFG::CHUNK values x CFG::BW_INP bits each),
//               then CFG::N_FLUSH trailing PAD (zero) windows; capture CFG::OUT_PER_SAMPLE
//               outputs (CFG::BW_OUT bits, sign-extended iff CFG::SIGNED_OUT).
//
// Contract (5-arg): size_t inference(c_inp, c_out, n_samples, inp_pause_prob, seed)
#pragma once
#include <verilated.h>
#include "ioutil.hh"
#include <cstdint>
#include <cstddef>
#include <memory>
#include <random>
#include <algorithm>

template <class CFG>
size_t stream_inference(const int32_t *c_inp, int32_t *c_out, size_t n_samples,
                        double inp_pause_prob, uint32_t seed) {
    auto dut = std::make_unique<typename CFG::dut_t>();
    std::mt19937 rng(seed);
    std::uniform_real_distribution<double> dist(0.0, 1.0);

    dut->clk = 1; dut->inp_valid = 0;
    for (size_t i = 0; i < sizeof(dut->model_inp) / sizeof(uint32_t); ++i)
        reinterpret_cast<uint32_t *>(&dut->model_inp)[i] = 0;

    const size_t per_sample  = CFG::WINDOWS + CFG::N_FLUSH;
    const size_t total_feeds = n_samples * per_sample;
    const size_t total_out   = n_samples * CFG::OUT_PER_SAMPLE;
    const size_t N_inp       = CFG::CHUNK * CFG::WINDOWS;
    size_t feed = 0, n_out = 0;
    int32_t pad[CFG::CHUNK] = {0};

    const size_t max_cycles =
        static_cast<size_t>(static_cast<double>(total_feeds) /
                            std::max(1.0 - inp_pause_prob, 0.05)) * 2 + 400;

    for (size_t cyc = 0; cyc < max_cycles; ++cyc) {
        if (feed < total_feeds) {
            bool pause = (inp_pause_prob > 0.0) && (dist(rng) < inp_pause_prob);
            if (!pause) {
                size_t s = feed / per_sample, w = feed % per_sample;
                if (w < CFG::WINDOWS)
                    write_input<CFG::CHUNK, CFG::BW_INP>(dut->model_inp, &c_inp[N_inp * s + CFG::CHUNK * w]);
                else
                    write_input<CFG::CHUNK, CFG::BW_INP>(dut->model_inp, pad);
                dut->inp_valid = 1; ++feed;
            } else dut->inp_valid = 0;
        } else dut->inp_valid = 0;

        dut->clk = 0; dut->eval();
        dut->clk = 1; dut->eval();

        if (dut->out_valid == 1 && n_out < total_out) {
            int32_t raw;
            read_output<1, CFG::BW_OUT>(dut->model_out, &raw);
            if (CFG::SIGNED_OUT) {
                const int32_t m = int32_t(1) << (CFG::BW_OUT - 1);
                raw = (raw ^ m) - m;
            }
            c_out[n_out++] = raw;
        }
        if (feed >= total_feeds && n_out >= total_out) break;
    }
    dut->final();
    return n_out;
}
