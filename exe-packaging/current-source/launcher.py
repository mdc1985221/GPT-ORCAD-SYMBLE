"""Desktop entry point for the current source tree, without a console window."""
from pathlib import Path
import argparse
import ctypes
import os
import sys
import traceback

ROOT=Path(__file__).resolve().parents[2]
APP=ROOT/'orcad-assistant'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    logs=APP/'workspace';logs.mkdir(parents=True,exist_ok=True)
    sys.stdout=(logs/'desktop-launcher.log').open('a',encoding='utf8',buffering=1)
    sys.stderr=sys.stdout
    os.chdir(ROOT)
    sys.path.insert(0,str(APP))
    try:
        import web_app
        web_app.serve(args.port,not args.no_browser)
    except Exception:
        traceback.print_exc()
        ctypes.windll.user32.MessageBoxW(None,'启动失败，请查看：'+str(logs/'desktop-launcher.log'),'Cadence 器件助手',16)
        raise

if __name__=='__main__':main()
