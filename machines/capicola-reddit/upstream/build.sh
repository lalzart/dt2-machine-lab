#!/usr/bin/env bash
# build.sh -- set up everything dt2-capicola needs and build the OS image.
#
#   ./build.sh --stock Digitakt_II_OS1.17.syx      (or Elektron's .zip)
#
# 1. installs the tools that are missing (asks first): Homebrew on macOS,
#    apt on Debian/Ubuntu;
# 2. clones dn2_firmware_explore and selache (and digikit, for --tests) into
#    deps/ at the commits this repository was tested with, and builds selache;
# 3. copies Elektron's OS file into deps/stock/ (its version is read from its hash);
# 4. builds the DSP code and the image: out/dt2capicola_DT2_<OS>.syx.
#
# Run it again at any time: what is already in place is kept.
set -euo pipefail

REPO=$(cd "$(dirname "$0")" && pwd)
DEPS=${DT2_DEPS:-$REPO/deps}
OUT=$REPO/out

# The dependencies, at the commits the tests pass with.
DNFW_URL=https://github.com/angellinares/dn2_firmware_explore.git
DNFW_REV=b8a07f3a0623a2c0a9e8fd25dae9483aa0081952
SELACHE_URL=https://github.com/js216/selache.git
SELACHE_REV=2b26d3b75c53063575bc5c820fa0d38879335187
DIGIKIT_URL=https://github.com/m-dwyer/digikit.git
DIGIKIT_REV=39f8f20da7950724511ea06e99af23ab928cc0cf

usage() {
  cat <<'EOF'
Usage: ./build.sh [--stock FILE] [options]

  --stock FILE     Elektron's Digitakt II OS file (.syx, or the .zip from
                   Elektron's site): OS 1.17 or 1.16. Needed the first time;
                   after that the copy in deps/stock/ is used.
  --os VERSION     which OS to build for when deps/stock/ holds more than one
                   (default: 1.17 if present)
  --diag           also build the diag image (USB probe and load counters, for
                   firmware/dt2probe.py capload)
  --no-slice-ui    leave SLICE and GRID as stock (STRETCH and REPITCH only)
  --tests          also set up digikit and run the test suite
  --yes            install missing tools without asking
  -h, --help       this text

The image is written to out/. Send it to the Digitakt II with Elektron Transfer.
Unofficial software: read README.md first.
EOF
}

STOCK_IN="" OS="" DIAG=0 SLICE_UI=1 TESTS=0 YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --stock) STOCK_IN=${2:?--stock needs a file}; shift 2 ;;
    --os) OS=${2:?--os needs a version}; shift 2 ;;
    --diag) DIAG=1; shift ;;
    --no-slice-ui) SLICE_UI=0; shift ;;
    --tests) TESTS=1; shift ;;
    --yes|-y) YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

step() { printf '\n==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }
# runs TOOL ARG...: the tool is there AND works. On macOS /usr/bin/git, cc, clang
# and python3 are all one stub that ships with the system and only runs once the
# Xcode command line tools are installed, so `command -v` alone says yes on a Mac
# where none of them work.
runs() { command -v "$1" >/dev/null 2>&1 && "$@" >/dev/null 2>&1; }

confirm() {   # confirm "question": yes with --yes; no answer possible -> no
  [ "$YES" = 1 ] && return 0
  [ -t 0 ] || return 1
  printf '%s [y/N] ' "$1"
  read -r a
  case "$a" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

m68k_prefix() {
  for p in m68k-elf- m68k-linux-gnu- m68k-none-elf-; do
    have "${p}as" && have "${p}ld" && have "${p}objcopy" && have "${p}nm" && { echo "$p"; return 0; }
  done
  return 1
}

m68k_gcc() {
  for p in m68k-elf- m68k-linux-gnu- m68k-none-elf-; do have "${p}gcc" && return 0; done
  return 1
}

# ---- 1. tools ---------------------------------------------------------------

step "Checking tools"
[ -x "$HOME/.local/bin/uv" ] && PATH="$HOME/.local/bin:$PATH"
[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
# Homebrew is often installed but left off PATH (its installer prints the line to
# add and leaves it to you), so look where it puts itself before deciding it is missing
if ! have brew; then
  for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [ -x "$b" ] && eval "$("$b" shellenv)" && break
  done
fi

# macOS: the Xcode command line tools come first. Without them git, cc, clang and
# python3 are one stub that opens an installer window and fails, so every check
# below would pass on a Mac where none of them work.
if [ "$(uname -s)" = Darwin ] && ! { xcode-select -p >/dev/null 2>&1 && runs git --version && runs cc --version; }; then
  echo "The Xcode command line tools are missing. git, clang and make come from them,"
  echo "and macOS does not install them until something asks."
  if confirm "Open Apple's installer for them now?"; then
    xcode-select --install 2>/dev/null || true
    die "finish the install in the window that just opened, then run ./build.sh again"
  fi
  die "install them with 'xcode-select --install', then run ./build.sh again"
fi

missing=()
for t in git python3 cc clang; do runs "$t" --version || missing+=("$t"); done
for t in cargo uv; do have "$t" || missing+=("$t"); done
m68k_prefix >/dev/null || missing+=("m68k-binutils")
# the m68k compiler builds the probe, which only the diag image carries
if [ "$DIAG" = 1 ] && ! m68k_gcc; then missing+=("m68k-gcc"); fi

if [ ${#missing[@]} -gt 0 ]; then
  echo "missing: ${missing[*]}"
  case "$(uname -s)" in
    Darwin)
      if ! have brew; then
        echo "Homebrew (https://brew.sh) is how macOS gets the m68k tools; nothing else provides them."
        confirm "Install Homebrew now? It asks for your password and takes a few minutes." \
          || die "Homebrew is needed: install it from https://brew.sh, then run ./build.sh again"
        NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do
          [ -x "$b" ] && eval "$("$b" shellenv)" && break
        done
        have brew || die "Homebrew is installed but not on this shell's PATH: open a new Terminal window and run ./build.sh again"
      fi
      pkgs=()
      for t in "${missing[@]}"; do
        case "$t" in
          git) pkgs+=(git) ;; uv) pkgs+=(uv) ;; cargo) pkgs+=(rust) ;;
          m68k-binutils) pkgs+=(m68k-elf-binutils) ;; m68k-gcc) pkgs+=(m68k-elf-gcc) ;;
        esac
      done
      if [ ${#pkgs[@]} -gt 0 ]; then
        echo "will run: brew install ${pkgs[*]}"
        confirm "Install them now?" || die "not installed; install them yourself or run ./build.sh --yes"
        brew install "${pkgs[@]}"
      fi
      ;;
    Linux)
      have apt-get || die "install these yourself (no apt-get here): ${missing[*]}; see README.md"
      SUDO=""; [ "$(id -u)" = 0 ] || SUDO=sudo
      apt_pkgs=(git python3 build-essential clang curl ca-certificates binutils-m68k-linux-gnu gcc-m68k-linux-gnu)
      echo "will run: $SUDO apt-get install ${apt_pkgs[*]}"
      have cargo || echo "will install Rust with rustup (https://rustup.rs)"
      have uv || echo "will install uv (https://astral.sh/uv)"
      confirm "Install them now?" || die "not installed; install them yourself or run ./build.sh --yes"
      $SUDO apt-get update -q
      DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -q "${apt_pkgs[@]}"
      if ! have cargo; then
        curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
        . "$HOME/.cargo/env"
      fi
      if ! have uv; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
        PATH="$HOME/.local/bin:$PATH"
      fi
      ;;
    *)
      die "install these yourself: ${missing[*]} (macOS and Debian/Ubuntu are automated; on Windows use WSL)" ;;
  esac
  for t in git python3 cc clang; do runs "$t" --version || die "$t is still missing"; done
  for t in cargo uv; do have "$t" || die "$t is still missing"; done
  m68k_prefix >/dev/null || die "m68k binutils are still missing"
fi
echo "ok: git, python3, cc, clang, cargo, uv, $(m68k_prefix)binutils"

# ---- 2. dependencies ----------------------------------------------------------

clone_at() {   # clone_at URL REV DIR: DIR checked out at REV (a clone with local changes is left alone)
  local url=$1 rev=$2 dir=$3
  if [ ! -d "$dir/.git" ]; then
    git clone --quiet "$url" "$dir"
  fi
  if [ "$(git -C "$dir" rev-parse HEAD)" != "$rev" ]; then
    if [ -n "$(git -C "$dir" status --porcelain --untracked-files=no)" ]; then
      echo "warning: $dir has local changes; leaving it as it is (not at $rev)"
      return 0
    fi
    git -C "$dir" cat-file -e "$rev^{commit}" 2>/dev/null || git -C "$dir" fetch --quiet origin
    git -C "$dir" checkout --quiet --detach "$rev"
  fi
  echo "ok: $(basename "$dir") at ${rev:0:7}"
}

step "Fetching dependencies into ${DEPS#$REPO/}/"
mkdir -p "$DEPS"
clone_at "$DNFW_URL" "$DNFW_REV" "$DEPS/dn2_firmware_explore"
clone_at "$SELACHE_URL" "$SELACHE_REV" "$DEPS/selache"
if [ "$(cat "$DEPS/selache/target/.dt2-built" 2>/dev/null)" != "$(git -C "$DEPS/selache" rev-parse HEAD)" ] \
   || [ ! -x "$DEPS/selache/target/release/selcc" ]; then
  step "Building selache (the SHARC toolchain; a few minutes the first time)"
  (cd "$DEPS/selache" && cargo build --release --quiet)
  git -C "$DEPS/selache" rev-parse HEAD > "$DEPS/selache/target/.dt2-built"
fi
echo "ok: selache built"
if [ "$TESTS" = 1 ]; then
  clone_at "$DIGIKIT_URL" "$DIGIKIT_REV" "$DEPS/digikit"
  (cd "$DEPS/digikit" && uv sync --quiet)
  echo "ok: digikit set up"
fi

# ---- 3. Elektron's OS file ----------------------------------------------------

os_of() {   # the OS version of an Elektron .syx (firmware/fwver.py's known hashes), or nothing
  python3 - "$1" <<'EOF'
import hashlib, sys
sys.path.insert(0, "firmware")
import fwver
h = hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest()
print(next((v for v, (_, s) in fwver.KNOWN.items() if s == h), ""))
EOF
}

cd "$REPO"
mkdir -p "$DEPS/stock"
if [ -n "$STOCK_IN" ]; then
  [ -f "$STOCK_IN" ] || die "no such file: $STOCK_IN"
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  case "$STOCK_IN" in
    *.zip|*.ZIP)
      python3 - "$STOCK_IN" "$tmp/stock.syx" <<'EOF'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
# (a zip repacked on macOS carries a __MACOSX/._name copy of every file: not one of them)
names = [n for n in z.namelist() if n.lower().endswith(".syx")
         and not n.startswith("__MACOSX/") and not n.rsplit("/", 1)[-1].startswith("._")]
if len(names) != 1:
    sys.exit(f"the zip holds {len(names)} .syx files, want one")
open(sys.argv[2], "wb").write(z.read(names[0]))
EOF
      ;;
    *) cp "$STOCK_IN" "$tmp/stock.syx" ;;
  esac
  v=$(os_of "$tmp/stock.syx")
  [ -n "$v" ] || die "$STOCK_IN is not an Elektron Digitakt II OS this mod knows (1.17 or 1.16, unmodified)"
  cp "$tmp/stock.syx" "$DEPS/stock/Digitakt_II_OS$v.syx"
  echo "ok: Elektron OS $v"
  [ -n "$OS" ] || OS=$v
fi
if [ -z "$OS" ]; then
  for v in 1.17 1.16; do [ -f "$DEPS/stock/Digitakt_II_OS$v.syx" ] && { OS=$v; break; }; done
fi
[ -n "$OS" ] || die "give Elektron's OS file the first time: ./build.sh --stock Digitakt_II_OS1.17.syx"
[ -f "$DEPS/stock/Digitakt_II_OS$OS.syx" ] || die "no Elektron OS $OS file in deps/stock/: give it with --stock"

# ---- 4. build -------------------------------------------------------------------

export DT2_FW=$OS DT2_DEPS=$DEPS SELACHE=$DEPS/selache DNFW_SRC=$DEPS/dn2_firmware_explore/src
export DT2_STOCK_SYX=$DEPS/stock/Digitakt_II_OS$OS.syx
mkdir -p "$OUT"
LOG=$OUT/build.log
: > "$LOG"
run() {   # run DESCRIPTION CMD...: the output to out/build.log, its end shown if it fails
  step "$1"; shift
  if ! "$@" >> "$LOG" 2>&1; then
    tail -20 "$LOG" >&2
    die "failed (the whole output is in out/build.log)"
  fi
}
run "Building the DSP code" sh tools/build_gen.sh
UI=(); [ "$SLICE_UI" = 1 ] && UI=(--slice-ui)
IMAGE=$OUT/dt2capicola_DT2_$OS.syx
run "Building the OS image for Digitakt II OS $OS" \
  uv run --quiet --python 3.12 --no-project python firmware/build_cap.py --release ${UI[@]+"${UI[@]}"} -o "$IMAGE"
grep -q "all checks pass" "$LOG" || die "the image builder did not confirm its checks (see out/build.log)"
if [ "$DIAG" = 1 ]; then
  DIAG_IMAGE=$OUT/dt2capdiag_DT2_$OS.syx
  run "Building the diag image" \
    uv run --quiet --python 3.12 --no-project python firmware/build_cap.py --diag ${UI[@]+"${UI[@]}"} -o "$DIAG_IMAGE"
fi
if [ "$TESTS" = 1 ]; then
  step "Running the tests (about 6 minutes)"
  DIGIKIT=$DEPS/digikit python3 test/run_tests.py all
fi

step "Done"
echo "  $IMAGE"
[ "$DIAG" = 1 ] && echo "  $DIAG_IMAGE (diag)"
cat <<'EOF'

Send the image to the Digitakt II with Elektron Transfer, as for any OS update.
This is unofficial software: back up your projects first, and see README.md for
how to go back to the stock OS.
EOF
