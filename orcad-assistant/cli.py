"""Headless entry point for the same desktop project pipeline."""
import argparse
import json
from pathlib import Path
import assistant_core as core
import build_pipeline

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='OrCAD 符号助手 · 项目构建')
    parser.add_argument('project', help='项目 JSON')
    parser.add_argument('--environment', help='环境 JSON')
    parser.add_argument('--output', default='workspace/output')
    parser.add_argument('--preview-only', action='store_true')
    args = parser.parse_args()
    project = core.load_project(args.project)
    env = core.DEFAULT_ENV.copy()
    if args.environment:
        env.update(json.loads(Path(args.environment).read_text(encoding='utf-8')))
    if args.preview_only:
        cfg, pins = core.layout(project, env)
        target = Path(args.output)
        target.mkdir(parents=True, exist_ok=True)
        core.export_svg(cfg, pins, target / 'preview.svg')
        print(target / 'preview.svg')
    else:
        print(json.dumps(build_pipeline.build(project, env, args.output, print), ensure_ascii=False, indent=2))
