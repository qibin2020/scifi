default: slow

VERILATOR_ROOT = $(shell verilator -V | grep -a VERILATOR_ROOT | tail -1 | awk '{print $$3}')
INCLUDES = -I./obj_dir -I$(VERILATOR_ROOT)/include
WARNINGS = -Wl,--no-undefined
CFLAGS = -std=c++17 -fPIC
LINKFLAGS = $(INCLUDES) $(WARNINGS)
VM_PREFIX ?= stream_wrapper
STAMP ?= $(shell cat .stamp 2>/dev/null || (uuidgen > .stamp && cat .stamp))
LIBNAME = lib$(VM_PREFIX)_$(STAMP).so
N_JOBS ?= $(shell nproc)

# ---------- Verilate & build static libs ----------
./obj_dir/libV$(VM_PREFIX).a ./obj_dir/libverilated.a ./obj_dir/V$(VM_PREFIX)__ALL.a: src/$(VM_PREFIX).v
	verilator --cc -j $(N_JOBS) -build src/$(VM_PREFIX).v \
		--prefix V$(VM_PREFIX) \
		--top-module $(VM_PREFIX) \
		-Wall \
		-CFLAGS "$(CFLAGS)" \
		-Isrc -Isrc/static

# ---------- Link shared library ----------
$(LIBNAME): ./obj_dir/libV$(VM_PREFIX).a ./obj_dir/libverilated.a ./obj_dir/V$(VM_PREFIX)__ALL.a $(VM_PREFIX)_binder.cc
	$(CXX) $(CFLAGS) $(LINKFLAGS) $(CXXFLAGS) -pthread -shared -o $(LIBNAME) \
		$(VM_PREFIX)_binder.cc \
		./obj_dir/libV$(VM_PREFIX).a \
		./obj_dir/libverilated.a \
		./obj_dir/V$(VM_PREFIX)__ALL.a

fast: CFLAGS += -O3
fast: $(LIBNAME)

slow: CFLAGS += -O
slow: $(LIBNAME)

clean:
	rm -rf obj_dir .stamp
	rm -f lib*.so
