"""CLI entry point: python -m transcribe …"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from transcribe.errors import JobConflictError, ProviderError, TranscribeError
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.providers.ollama import OllamaVisionProvider, is_loopback_host, normalize_base_url
from transcribe.services.export import ExportService
from transcribe.services.job import build_coordinator
from transcribe.services.project import ProjectService, open_project_paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="transcribe", description="Local notebook OCR")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Create a new project directory")
    p_init.add_argument("project", type=Path)
    p_init.add_argument("--title", default="Untitled notebook")

    p_import = sub.add_parser("import", help="Import an image or PDF into a project")
    p_import.add_argument("project", type=Path)
    p_import.add_argument("source", type=Path)
    p_import.add_argument("--dpi", type=int, default=200)

    p_models = sub.add_parser("models", help="List vision-capable Ollama models")
    p_models.add_argument("--base-url", default="http://localhost:11434")
    p_models.add_argument("--all", action="store_true", help="List all models")
    p_models.add_argument("--refresh", action="store_true")

    p_run = sub.add_parser("run", help="Run OCR on project pages")
    p_run.add_argument("project", type=Path)
    p_run.add_argument("--model", required=True)
    p_run.add_argument("--base-url", default=None)
    p_run.add_argument("--force", action="store_true")
    p_run.add_argument("--workers", type=int, default=1)
    p_run.add_argument("--allow-remote-ollama", action="store_true")

    p_export = sub.add_parser("export", help="Export markdown/text/notebook JSON")
    p_export.add_argument("project", type=Path)
    p_export.add_argument("dest", type=Path, nargs="?", default=None)

    p_status = sub.add_parser("status", help="Show project page statuses")
    p_status.add_argument("project", type=Path)

    args = parser.parse_args(argv)
    clock = SystemClock()
    ids = UuidGenerator()

    try:
        if args.cmd == "init":
            paths = open_project_paths(args.project)
            ProjectService(paths, clock=clock, ids=ids).create(title=args.title)
            print(f"Created project at {paths.root}")
            return 0

        if args.cmd == "models":
            url = normalize_base_url(args.base_url)
            if not is_loopback_host(url):
                print(
                    "WARNING: Ollama host is not loopback; images would leave this machine.",
                    file=sys.stderr,
                )
            provider = OllamaVisionProvider(url)
            result = (
                provider.list_models(refresh=args.refresh)
                if args.all
                else provider.list_vision_models(refresh=args.refresh)
            )
            if result.error:
                print(f"Discovery warning: {result.error}", file=sys.stderr)
            if not result.models:
                print("No models found.")
                return 1
            for m in result.models:
                caps = ",".join(m.capabilities) if m.capability_known else "unknown"
                print(f"{m.name}\tdigest={m.digest or '-'}\tcapabilities={caps}")
            return 0

        paths, projects, coord, ingest = build_coordinator(
            args.project, clock=clock, ids=ids
        )

        if args.cmd == "import":
            project = projects.load()
            project = ingest.import_path(project, args.source, render_dpi=args.dpi)
            print(f"Imported {args.source.name}: {project.pages[-1].page_index + 1 if project.pages else 0} page(s); total pages={len(project.pages)}")
            return 0

        if args.cmd == "status":
            project = projects.load()
            for i, page in enumerate(project.pages):
                result = projects.load_page_result(page.page_id)
                status = result.status if result else "pending"
                edited = " edited" if result and result.edited_text is not None else ""
                print(f"{i:04d}  {page.page_id}  {status}{edited}")
            return 0

        if args.cmd == "run":
            project = projects.load()
            settings = project.settings
            settings.model_name = args.model
            if args.base_url:
                settings.base_url = normalize_base_url(args.base_url)
            settings.max_workers = max(1, min(2, args.workers))
            url = normalize_base_url(settings.base_url)
            if not is_loopback_host(url) and not args.allow_remote_ollama:
                print(
                    "Refusing non-loopback Ollama host without --allow-remote-ollama "
                    "(page images would leave this machine).",
                    file=sys.stderr,
                )
                return 2
            settings.allow_non_loopback = bool(args.allow_remote_ollama)
            project = projects.save_settings(project, settings)
            # Rebuild provider with updated URL
            from transcribe.providers.ollama import OllamaVisionProvider

            coord.provider = OllamaVisionProvider(settings.base_url)

            progress = coord.run_blocking(force=args.force)
            return 0 if progress.status == "completed" else 1

        if args.cmd == "export":
            project = projects.load()
            dest = args.dest or paths.exports_dir
            written = ExportService(paths, projects).export_all(project, dest)
            for kind, path in written.items():
                print(f"{kind}: {path}")
            return 0

        parser.error(f"unknown command {args.cmd}")
        return 2
    except (TranscribeError, JobConflictError, ProviderError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
