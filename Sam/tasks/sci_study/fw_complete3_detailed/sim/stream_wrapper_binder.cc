// VOID skeleton — empty C++ binder. You must implement this file from
// scratch. See top.md for the required contract.
//
// Hard contract (verify_golden.py loads this via ctypes — DO NOT change):
//
//   extern "C" size_t inference(
//       const int32_t *c_inp,         // n_samples * 500 int32 values
//       int32_t       *c_out,         // output buffer >= n_samples
//       size_t         n_samples,     // number of waveforms to process
//       double         inp_pause_prob, // [0,1) probability of dropping inp_valid
//       uint32_t       seed           // RNG seed for reproducible pauses
//   );
//   // returns: number of outputs collected
//
// You design the .v module port list AND the binder logic that drives it.
// The Verilator-generated header `Vstream_wrapper.h` will expose your .v
// ports as members of class Vstream_wrapper.
