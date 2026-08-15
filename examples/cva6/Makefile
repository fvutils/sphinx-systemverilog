# Build sphinx-systemverilog documentation for the CVA6 RISC-V core.
#
#   make fetch    # shallow-clone CVA6 into ./_cva6 (~100 MB, once)
#   make html     # build to ./_build/html
#   make open     # build and open in a browser
#   make clean    # remove the build output (keeps ./_cva6)
#   make distclean
#
# Point at an existing checkout instead of cloning:
#   make html CVA6_ROOT=/path/to/cva6
#
# Choose a different core configuration:
#   make html TARGET_CFG=cv32a65x

CVA6_URL    ?= https://github.com/openhwgroup/cva6.git
CVA6_ROOT   ?= $(CURDIR)/_cva6
TARGET_CFG  ?= cv64a6_imafdc_sv39
BUILDDIR    ?= _build
SPHINXBUILD ?= python -m sphinx
SPHINXOPTS  ?=

export CVA6_ROOT
export TARGET_CFG

.PHONY: all fetch html open clean distclean

all: html

fetch: $(CVA6_ROOT)/core/Flist.cva6

$(CVA6_ROOT)/core/Flist.cva6:
	@echo "Cloning CVA6 into $(CVA6_ROOT) (shallow, ~100 MB)..."
	git clone --depth 1 $(CVA6_URL) $(CVA6_ROOT)
	@echo "Fetching the two submodules the core filelist needs (~7 MB)..."
	cd $(CVA6_ROOT) && git submodule update --init --depth 1 \
		core/cvfpu core/cache_subsystem/hpdcache
	@echo
	@echo "Done.  CVA6 has 18 submodules; only these two are RTL the core"
	@echo "filelist references.  The rest are verification and toolchain."

html:
	$(SPHINXBUILD) -b html $(SPHINXOPTS) . $(BUILDDIR)/html
	@echo
	@echo "Built: $(BUILDDIR)/html/index.html"

open: html
	@python -c "import webbrowser,os;webbrowser.open('file://'+os.path.abspath('$(BUILDDIR)/html/index.html'))"

clean:
	rm -rf $(BUILDDIR)

distclean: clean
	rm -rf $(CVA6_ROOT)
