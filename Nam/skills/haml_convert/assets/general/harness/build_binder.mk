# build_binder.mk — verilate stream_wrapper.v + compile binder + link .so
#
# Inputs:
#   ./src/stream_wrapper.v + ./src/{kernel,dense}_wrapper.v + ./src/static/*.v
# Outputs:
#   libstream_wrapper_<stamp>.so (loadable by verify_golden.py via ctypes)
#
# Use:
#   make -f build_binder.mk slow     # -O (faster build, slower exec)
#   make -f build_binder.mk fast     # -O3
#   make -f build_binder.mk clean

VM_PREFIX ?= stream_wrapper
STAMP     ?= dev
LIBNAME    = lib$(VM_PREFIX)_$(STAMP).so
N_JOBS    ?= $(shell nproc)

VERILATOR_ROOT := $(shell verilator -V | grep -a VERILATOR_ROOT | tail -1 | awk '{print $$3}')
INCLUDES        = -I./obj_dir -I$(VERILATOR_ROOT)/include -I./src -I.
CFLAGS          = -std=c++17 -fPIC
LINKFLAGS       = $(INCLUDES) -Wl,--no-undefined
VERILATOR_FLAGS ?=

default: slow

./obj_dir/V$(VM_PREFIX)__ALL.a: ./src/$(VM_PREFIX).v $(wildcard ./src/*.v) $(wildcard ./src/static/*.v)
	mkdir -p obj_dir
	verilator --cc -j $(N_JOBS) -build ./src/$(VM_PREFIX).v \
	    --prefix V$(VM_PREFIX) $(VERILATOR_FLAGS) \
	    -CFLAGS "$(CFLAGS)" -I./src -I./src/static

$(LIBNAME): ./obj_dir/V$(VM_PREFIX)__ALL.a $(VM_PREFIX)_binder.cc
	$(CXX) $(CFLAGS) $(LINKFLAGS) -pthread -shared -o $(LIBNAME) \
	    $(VM_PREFIX)_binder.cc \
	    ./obj_dir/libV$(VM_PREFIX).a \
	    ./obj_dir/libverilated.a \
	    ./obj_dir/V$(VM_PREFIX)__ALL.a

slow: CFLAGS += -O
slow: $(LIBNAME)

fast: CFLAGS += -O3
fast: $(LIBNAME)

clean:
	rm -rf obj_dir
	rm -f lib$(VM_PREFIX)_*.so
