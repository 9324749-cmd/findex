from .index import build_index, save_index
import argparse
def main():
 p=argparse.ArgumentParser(); p.add_argument("corpus", nargs="?", default="data/"); p.add_argument("--out", default="index.bin"); p.add_argument("--format", choices=["pickle","json"], default="pickle"); a=p.parse_args(); ix=build_index(a.corpus); save_index(ix,a.out,a.format); print(ix)
if __name__ == "__main__": main()
