"""CLI entry point: python -m transcribe …"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from transcribe.errors import (
    JobConflictError,
    ProviderError,
    TranscribeError,
    ValidationError,
)
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.providers.ollama import (
    OllamaVisionProvider,
    is_local_machine_host,
    normalize_base_url,
)
from transcribe.runtime_paths import PATHS, default_ollama_base_url
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
    p_models.add_argument("--base-url", default=None)
    p_models.add_argument("--all", action="store_true", help="List all models")
    p_models.add_argument("--refresh", action="store_true")

    p_run = sub.add_parser("run", help="Run OCR on project pages")
    p_run.add_argument("project", type=Path)
    p_run.add_argument("--model", required=True)
    p_run.add_argument("--base-url", default=None)
    p_run.add_argument("--force", action="store_true")
    p_run.add_argument("--workers", type=int, default=1)
    p_run.add_argument("--allow-remote-ollama", action="store_true")
    p_run.add_argument(
        "--cleanup",
        action="store_true",
        help="Enable optional post-OCR text-model cleanup",
    )
    p_run.add_argument(
        "--cleanup-mode",
        choices=["strip_leak", "sanitize_light", "rewrite"],
        default=None,
        help="Cleanup mode (requires --cleanup)",
    )
    p_run.add_argument(
        "--cleanup-model",
        default=None,
        help="Text model for cleanup (defaults to project text analysis model)",
    )

    p_multi = sub.add_parser(
        "multipass",
        help="Run multiple vision OCR models then rank/composite",
    )
    p_multi.add_argument("project", type=Path)
    p_multi.add_argument(
        "--model",
        action="append",
        dest="models",
        required=False,
        help="Vision model (repeat; at least two). Not required with --resume",
    )
    p_multi.add_argument("--base-url", default=None)
    p_multi.add_argument("--force", action="store_true")
    p_multi.add_argument("--allow-remote-ollama", action="store_true")
    p_multi.add_argument(
        "--no-auto-composite",
        action="store_true",
        help="Do not auto-activate composite candidates",
    )
    p_multi.add_argument(
        "--text-model",
        default=None,
        help="Text model for rank/composite (defaults to project cleanup/text model)",
    )
    p_multi.add_argument(
        "--resume",
        default=None,
        metavar="PASS_ID",
        help="Resume an incomplete multipass job by pass_id",
    )
    p_multi.add_argument(
        "--cleanup",
        action="store_true",
        help="Run post-OCR text-model cleanup on vision phases (off by default)",
    )

    p_ft = sub.add_parser(
        "export-finetune",
        help="Export preferred/active OCR + images for external fine-tuning",
    )
    p_ft.add_argument("project", type=Path)
    p_ft.add_argument("dest", type=Path, nargs="?", default=None)
    p_ft.add_argument("--require-preferred", action="store_true")
    p_ft.add_argument("--include-rejected", action="store_true")
    p_ft.add_argument("--no-edited", action="store_true", help="Skip pages with human edits")
    p_ft.add_argument("--hardlink-images", action="store_true")

    p_models.add_argument(
        "--prefs",
        action="store_true",
        help="Show preference stats beside each model",
    )

    p_export = sub.add_parser(
        "export",
        help="Export notebook formats (json/markdown/text/html/epub/pdf)",
    )
    p_export.add_argument(
        "project",
        type=Path,
        nargs="?",
        default=None,
        help="Primary project path (optional when --notebooks is used)",
    )
    p_export.add_argument("dest", type=Path, nargs="?", default=None)
    p_export.add_argument(
        "--notebooks",
        type=Path,
        nargs="+",
        default=None,
        help="One or more notebook roots (anthology export when multiple)",
    )
    p_export.add_argument(
        "--format",
        dest="formats",
        action="append",
        default=None,
        help="Format to include (repeatable): json, markdown, text, html, epub, pdf",
    )
    p_export.add_argument(
        "--profile",
        default=None,
        help="Export profile name (default/readable/compact/large_print or user)",
    )
    p_export.add_argument("--body-font", choices=["serif", "sans", "mono"], default=None)
    p_export.add_argument("--body-size", type=float, default=None)
    p_export.add_argument("--line-height", type=float, default=None)
    p_export.add_argument("--margin", type=float, default=None)
    p_export.add_argument(
        "--page-breaks",
        choices=["per_page", "continuous"],
        default=None,
    )
    p_export.add_argument("--title", default=None, help="Override anthology title")

    p_status = sub.add_parser("status", help="Show project page statuses")
    p_status.add_argument("project", type=Path)

    p_doctor = sub.add_parser("doctor", help="Validate project integrity")
    p_doctor.add_argument("project", type=Path)
    p_doctor.add_argument(
        "--deep",
        action="store_true",
        help="Hash source/render files and verify against the manifest",
    )

    p_detect = sub.add_parser("detect", help="Run a notebook content detector")
    p_detect.add_argument("project", type=Path)
    p_detect.add_argument(
        "--detector",
        default="poetry",
        help="Detector id (default: poetry)",
    )
    p_detect.add_argument("--force", action="store_true")
    p_detect.add_argument(
        "--auto-tag",
        action="store_true",
        help="After publish, tag pages in findings with the detector finding type",
    )
    p_detect.add_argument(
        "--list",
        action="store_true",
        help="List available detectors and exit",
    )

    p_bulk = sub.add_parser(
        "bulk-import",
        help="Plan/commit a folder into the notebook corpus (ImportRun)",
    )
    bulk_sub = p_bulk.add_subparsers(dest="bulk_cmd", required=True)
    p_bulk_plan = bulk_sub.add_parser(
        "folder",
        help="Scan a folder, create an ImportRun, and commit it",
    )
    p_bulk_plan.add_argument("folder", type=Path, help="Folder of JPEG/PNG/PDF files")
    p_bulk_plan.add_argument(
        "--title",
        default=None,
        help="Notebook title (default: folder name)",
    )
    p_bulk_plan.add_argument(
        "--policy",
        choices=["skip_existing_v1", "create_duplicate_v1"],
        default="skip_existing_v1",
    )
    p_bulk_plan.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan and exit without committing",
    )
    p_bulk_folders = bulk_sub.add_parser(
        "folders",
        help="Scan a parent directory; each child folder becomes a notebook",
    )
    p_bulk_folders.add_argument(
        "parent",
        type=Path,
        help="Parent directory whose immediate child folders become notebooks",
    )
    p_bulk_folders.add_argument(
        "--policy",
        choices=["skip_existing_v1", "create_duplicate_v1"],
        default="skip_existing_v1",
    )
    p_bulk_folders.add_argument(
        "--on-existing",
        choices=["skip", "overwrite"],
        default="skip",
        help="When a child folder name already maps to a managed notebook",
    )
    p_bulk_folders.add_argument(
        "--confirm-overwrite",
        default=None,
        help="Required for --on-existing overwrite; must be exactly 'OVERWRITE ALL'",
    )
    p_bulk_folders.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the scan/plan and exit without committing or deleting",
    )
    p_bulk_status = bulk_sub.add_parser("status", help="Show ImportRun outcomes")
    p_bulk_status.add_argument("import_run_id")
    p_bulk_resume = bulk_sub.add_parser("resume", help="Resume a non-terminal ImportRun")
    p_bulk_resume.add_argument("import_run_id")
    p_corpus_doctor = sub.add_parser(
        "corpus-doctor",
        help="Validate workspace corpus index integrity",
    )
    p_corpus_doctor.add_argument(
        "--deep",
        action="store_true",
        help="Also deep-doctor each registered notebook",
    )

    p_backup = sub.add_parser(
        "backup",
        help="Create or verify a full-workspace backup ZIP",
    )
    backup_sub = p_backup.add_subparsers(dest="backup_cmd", required=True)
    p_backup_create = backup_sub.add_parser(
        "create",
        help="Write a workspace backup ZIP (notebooks + corpus + config)",
    )
    p_backup_create.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Destination .zip (default: {EXPORT}/backups/transcribe-workspace-<stamp>.zip)",
    )
    p_backup_create.add_argument(
        "--include-inbox",
        action="store_true",
        help="Also pack TRANSCRIBE_INBOX_DIR",
    )
    p_backup_create.add_argument(
        "--include-exports",
        action="store_true",
        help="Also pack TRANSCRIBE_EXPORT_DIR (skips the destination zip itself)",
    )
    p_backup_create.add_argument(
        "--force",
        action="store_true",
        help="Overwrite destination if the .zip already exists",
    )
    p_backup_verify = backup_sub.add_parser(
        "verify",
        help="Verify a workspace backup ZIP without changing the workspace",
    )
    p_backup_verify.add_argument("archive", type=Path)

    p_restore = sub.add_parser(
        "restore",
        help="Replace the current workspace from a backup ZIP",
    )
    p_restore.add_argument("archive", type=Path)
    p_restore.add_argument(
        "--yes",
        action="store_true",
        help="Confirm replace (required to write)",
    )
    p_restore.add_argument(
        "--no-safety-backup",
        action="store_true",
        help="Skip automatic pre-restore safety ZIP",
    )
    p_restore.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify and describe replace plan without writing",
    )

    p_bulk_run = sub.add_parser(
        "bulk-run",
        help="Run OCR across many notebooks (OcrBatchRun)",
    )
    bulk_run_sub = p_bulk_run.add_subparsers(dest="bulk_run_cmd", required=True)

    def _add_bulk_run_ocr_flags(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--model",
            action="append",
            required=True,
            help=("Vision model (repeat for multipass compare; " "one value = single-model batch)"),
        )
        parser.add_argument("--base-url", default=None)
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--workers", type=int, default=1)
        parser.add_argument("--allow-remote-ollama", action="store_true")
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help=(
                "Single-model: enable post-OCR text cleanup. "
                "Multipass (≥2 --model): opt in vision-phase cleanup during compare"
            ),
        )
        parser.add_argument(
            "--cleanup-mode",
            choices=["strip_leak", "sanitize_light", "rewrite"],
            default=None,
        )
        parser.add_argument("--cleanup-model", default=None)
        parser.add_argument(
            "--text-model",
            default=None,
            help="Text model for multipass rank/composite (and cleanup when unset)",
        )
        parser.add_argument(
            "--no-auto-composite",
            action="store_true",
            help="Multipass: do not auto-activate composite candidates",
        )

    p_br_pending = bulk_run_sub.add_parser(
        "pending",
        help="OCR corpus notebooks that still have untranscribed or failed pages",
    )
    _add_bulk_run_ocr_flags(p_br_pending)
    p_br_import = bulk_run_sub.add_parser(
        "import-run",
        help="OCR notebooks committed by an ImportRun",
    )
    p_br_import.add_argument("import_run_id")
    _add_bulk_run_ocr_flags(p_br_import)
    p_br_nbs = bulk_run_sub.add_parser(
        "notebooks",
        help="OCR explicit notebook ids or project paths",
    )
    p_br_nbs.add_argument(
        "notebooks",
        nargs="+",
        help="Notebook id or project root (repeatable)",
    )
    _add_bulk_run_ocr_flags(p_br_nbs)
    p_br_status = bulk_run_sub.add_parser("status", help="Show OcrBatchRun outcomes")
    p_br_status.add_argument("ocr_run_id")
    p_br_resume = bulk_run_sub.add_parser("resume", help="Resume a non-terminal OcrBatchRun")
    p_br_resume.add_argument("ocr_run_id")

    p_bulk_ax = sub.add_parser(
        "bulk-analyse",
        help="Run Analyse across many notebooks (AnalysisBatchRun)",
    )
    bulk_ax_sub = p_bulk_ax.add_subparsers(dest="bulk_analyse_cmd", required=True)

    def _add_bulk_analyse_flags(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--preset",
            choices=["quick", "balanced", "thorough", "custom"],
            default="balanced",
            help="Analysis preset (default: balanced)",
        )
        parser.add_argument(
            "--module",
            action="append",
            default=[],
            help="Module id (repeatable; required when --preset custom)",
        )
        parser.add_argument(
            "--question",
            default=None,
            help="Optional Ask-notebook question (adds llm_custom_qa)",
        )
        parser.add_argument(
            "--text-model",
            default=None,
            help=(
                "Text Ollama model for LLM modules (frozen for the whole batch; "
                "defaults to notebook/workspace preference)"
            ),
        )

    p_ba_pending = bulk_ax_sub.add_parser(
        "pending",
        help="Analyse notebooks that need analysis (text + non-healthy)",
    )
    _add_bulk_analyse_flags(p_ba_pending)
    p_ba_import = bulk_ax_sub.add_parser(
        "import-run",
        help="Analyse notebooks committed by an ImportRun",
    )
    p_ba_import.add_argument("import_run_id")
    _add_bulk_analyse_flags(p_ba_import)
    p_ba_nbs = bulk_ax_sub.add_parser(
        "notebooks",
        help="Analyse explicit notebook ids or project paths",
    )
    p_ba_nbs.add_argument(
        "notebooks",
        nargs="+",
        help="Notebook id or project root (repeatable)",
    )
    _add_bulk_analyse_flags(p_ba_nbs)
    p_ba_status = bulk_ax_sub.add_parser("status", help="Show AnalysisBatchRun outcomes")
    p_ba_status.add_argument("analysis_batch_id")
    p_ba_resume = bulk_ax_sub.add_parser("resume", help="Resume a non-terminal AnalysisBatchRun")
    p_ba_resume.add_argument("analysis_batch_id")

    args = parser.parse_args(argv)
    clock = SystemClock()
    ids = UuidGenerator()

    try:
        if args.cmd == "bulk-import":
            return _cmd_bulk_import(args, clock=clock, ids=ids)
        if args.cmd == "bulk-run":
            return _cmd_bulk_run(args, clock=clock, ids=ids)
        if args.cmd == "bulk-analyse":
            return _cmd_bulk_analyse(args, clock=clock, ids=ids)
        if args.cmd == "corpus-doctor":
            return _cmd_corpus_doctor(args)
        if args.cmd == "backup":
            return _cmd_backup(args)
        if args.cmd == "restore":
            return _cmd_restore(args)

        if args.cmd == "init":
            paths = open_project_paths(args.project)
            ProjectService(paths, clock=clock, ids=ids).create(title=args.title)
            print(f"Created project at {paths.root}")
            return 0

        if args.cmd == "models":
            url = normalize_base_url(args.base_url or default_ollama_base_url())
            if not is_local_machine_host(url):
                print(
                    "WARNING: Ollama host is not on this machine; images would leave this machine.",
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
            prefs = None
            if getattr(args, "prefs", False):
                from transcribe.services.ocr_preference_stats import (
                    preference_hint_for_model,
                    rollup_preference_stats,
                )

                prefs = rollup_preference_stats()
            for m in result.models:
                caps = ",".join(m.capabilities) if m.capability_known else "unknown"
                line = f"{m.name}\tdigest={m.digest or '-'}\tcapabilities={caps}"
                if prefs is not None:
                    hint = preference_hint_for_model(m.name, stats=prefs)
                    if hint:
                        line = f"{line}\t{hint}"
                print(line)
            return 0

        if args.cmd == "export":
            return _cmd_export(args, clock=clock, ids=ids)

        if args.cmd == "export-finetune":
            return _cmd_export_finetune(args, clock=clock, ids=ids)

        paths, projects, coord, ingest = build_coordinator(args.project, clock=clock, ids=ids)

        if args.cmd == "import":
            projects.load()
            project = ingest.import_path(args.source, render_dpi=args.dpi)
            print(
                f"Imported {args.source.name}: {project.pages[-1].page_index + 1 if project.pages else 0} page(s); total pages={len(project.pages)}"
            )
            return 0

        if args.cmd == "status":
            project = projects.load()
            for i, page in enumerate(project.pages):
                result = projects.load_page_result(page.page_id)
                status = result.status if result else "pending"
                edited = " edited" if result and result.edited_text is not None else ""
                print(f"{i:04d}  {page.page_id}  {status}{edited}")
            return 0

        if args.cmd == "doctor":
            from transcribe.services.doctor import DoctorService

            report = DoctorService(paths, projects).run(deep=args.deep)
            for finding in report.findings:
                print(f"{finding.severity}: [{finding.code}] {finding.message}")
            if report.ok and not report.findings:
                print("ok: project integrity checks passed")
            elif report.ok:
                print("ok: no errors (warnings above)")
            return 0 if report.ok else 1

        if args.cmd == "run":
            project = projects.load()
            settings = project.settings
            settings.model_name = args.model
            if args.base_url:
                settings.base_url = normalize_base_url(args.base_url)
            settings.max_workers = max(1, min(2, args.workers))
            url = normalize_base_url(settings.base_url)
            if not is_local_machine_host(url) and not args.allow_remote_ollama:
                print(
                    "Refusing non-local Ollama host without --allow-remote-ollama "
                    "(page images would leave this machine).",
                    file=sys.stderr,
                )
                return 2
            settings.allow_non_loopback = bool(args.allow_remote_ollama)
            if args.cleanup:
                settings.cleanup_enabled = True
                if args.cleanup_mode:
                    settings.cleanup_mode = args.cleanup_mode
                if args.cleanup_model:
                    settings.cleanup_model_name = args.cleanup_model.strip()
            elif args.cleanup_mode or args.cleanup_model:
                print(
                    "error: --cleanup-mode / --cleanup-model require --cleanup",
                    file=sys.stderr,
                )
                return 2
            project = projects.save_settings(project, settings)
            coord.provider = OllamaVisionProvider(settings.base_url)

            progress = coord.run_blocking(force=args.force)
            return 0 if progress.status == "completed" else 1

        if args.cmd == "multipass":
            from transcribe.services.multipass import MultiPassCoordinator

            project = projects.load()
            settings = project.settings
            if args.base_url:
                settings.base_url = normalize_base_url(args.base_url)
            url = normalize_base_url(settings.base_url)
            if not is_local_machine_host(url) and not args.allow_remote_ollama:
                print(
                    "Refusing non-local Ollama host without --allow-remote-ollama "
                    "(page images would leave this machine).",
                    file=sys.stderr,
                )
                return 2
            settings.allow_non_loopback = bool(args.allow_remote_ollama)
            if args.text_model:
                settings.text_model_name = args.text_model.strip()
                if not settings.cleanup_model_name:
                    settings.cleanup_model_name = settings.text_model_name
            project = projects.save_settings(project, settings)
            coord.provider = OllamaVisionProvider(settings.base_url)
            multi = MultiPassCoordinator(jobs=coord, projects=projects, clock=clock, ids=ids)
            if args.resume:
                progress = multi.resume_blocking(args.resume)
            else:
                models = list(args.models or [])
                if len(models) < 2:
                    print(
                        "error: multipass requires at least two --model values "
                        "(or --resume PASS_ID)",
                        file=sys.stderr,
                    )
                    return 2
                progress = multi.run_blocking(
                    model_names=models,
                    force=args.force,
                    auto_activate_composite=not args.no_auto_composite,
                    cleanup_enabled=bool(args.cleanup),
                )
            return 0 if progress.status == "completed" else 1

        if args.cmd == "detect":
            from transcribe.detection.api import DetectionService

            if args.list:
                for info in DetectionService.list_detectors():
                    print(f"{info.detector_id}\tv{info.version}\t{info.title}")
                return 0
            svc = DetectionService(projects)
            result = svc.run_detector(args.detector, force=args.force, auto_tag=args.auto_tag)
            findings = result.get("findings") or []
            print(
                f"detector={args.detector} outcome={result.get('outcome')} "
                f"findings={len(findings)} windows={result.get('windows_scanned', 0)}"
            )
            for f in findings:
                print(
                    f"  {f.get('finding_type')} pages {f.get('start_page_id')}.."
                    f"{f.get('end_page_id')} confidence={f.get('confidence')}"
                )
            return (
                0
                if result.get("outcome")
                in ("success", "skipped_not_applicable", "insufficient_data")
                else 1
            )

        parser.error(f"unknown command {args.cmd}")
        return 2
    except (TranscribeError, JobConflictError, ProviderError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _cmd_export_finetune(args: argparse.Namespace, *, clock, ids) -> int:
    from transcribe.services.finetune_export import (
        FinetuneExportOptions,
        FinetuneExportService,
    )

    paths = open_project_paths(args.project)
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.load()
    opts = FinetuneExportOptions(
        include_edited_pages=not args.no_edited,
        require_preferred=bool(args.require_preferred),
        include_rejected_candidates=bool(args.include_rejected),
        image_mode="hardlink" if args.hardlink_images else "copy",
    )
    out = FinetuneExportService(paths, projects).export(args.dest, options=opts)
    print(f"Fine-tune export written to {out}")
    return 0


def _cmd_export(args: argparse.Namespace, *, clock, ids) -> int:
    from transcribe.config.defaults import builtin_profile_config
    from transcribe.config.profiles import load_profile_overlay
    from transcribe.services.export_options import ExportOptions, ExportTypography

    roots: list[Path] = []
    if args.notebooks:
        roots.extend(args.notebooks)
    if args.project is not None:
        if args.project not in roots:
            roots.insert(0, args.project)
    if not roots:
        print("error: provide a project path and/or --notebooks", file=sys.stderr)
        return 2

    base = ExportOptions()
    if args.profile:
        try:
            overlay = load_profile_overlay("export", args.profile)
        except Exception:
            overlay = builtin_profile_config("export", args.profile) or {}
        if overlay.get("export"):
            base = ExportOptions.from_dict(overlay["export"])

    formats = base.formats
    if args.formats:
        formats = frozenset(str(f).lower() for f in args.formats)  # type: ignore[arg-type]

    typo = base.typography
    typo = ExportTypography(
        body_font=args.body_font or typo.body_font,  # type: ignore[arg-type]
        body_size_pt=float(args.body_size if args.body_size is not None else typo.body_size_pt),
        line_height=float(args.line_height if args.line_height is not None else typo.line_height),
        paragraph_spacing_em=typo.paragraph_spacing_em,
        margin_in=float(args.margin if args.margin is not None else typo.margin_in),
        heading_scale=typo.heading_scale,
    )
    opts = ExportOptions(
        formats=formats,
        page_breaks=args.page_breaks or base.page_breaks,  # type: ignore[arg-type]
        include_dates=base.include_dates,
        include_blank_pages=base.include_blank_pages,
        title_page=base.title_page,
        typography=typo,
    )

    snapshots = []
    primary_paths = None
    primary_projects = None
    for root in roots:
        nb_paths = open_project_paths(root)
        nb_projects = ProjectService(nb_paths, clock=clock, ids=ids)
        if primary_paths is None:
            primary_paths = nb_paths
            primary_projects = nb_projects
        snapshots.append(ExportService.capture_snapshot_at(nb_paths, nb_projects))

    assert primary_paths is not None and primary_projects is not None
    if args.dest is not None:
        dest = args.dest
    elif os.getenv("TRANSCRIBE_EXPORT_DIR"):
        dest = PATHS.export_dir / primary_paths.root.name
    else:
        dest = primary_paths.exports_dir

    written = ExportService(primary_paths, primary_projects).export_snapshots(
        snapshots,
        dest_dir=dest,
        options=opts,
        title=args.title,
    )
    for kind, path in written.items():
        print(f"{kind}: {path}")
    return 0


def _cmd_bulk_import(args: argparse.Namespace, *, clock, ids) -> int:
    from transcribe.corpus.adapters import plan_from_folder, plan_from_folders
    from transcribe.corpus.folder_overwrite import prepare_folder_overwrite
    from transcribe.corpus.import_run import ImportRunStore
    from transcribe.corpus.orchestrator import ImportOrchestrator
    from transcribe.corpus.paths import CorpusPaths
    from transcribe.corpus.plan import (
        POLICY_CREATE_DUPLICATE_V1,
        POLICY_SKIP_EXISTING_V1,
    )

    corpus = CorpusPaths.from_runtime(PATHS)
    orchestrator = ImportOrchestrator(corpus, clock=clock, ids=ids)
    if args.bulk_cmd == "folder":
        policy = (
            POLICY_CREATE_DUPLICATE_V1
            if args.policy == "create_duplicate_v1"
            else POLICY_SKIP_EXISTING_V1
        )
        plan = plan_from_folder(
            args.folder,
            ids=ids,
            title=args.title,
            import_policy_id=policy,
        )
        print(
            f"plan_id={plan.plan_id} items={len(plan.items)} "
            f"policy={plan.import_policy_id} fingerprint={plan.fingerprint()[:12]}…"
        )
        for item in plan.items:
            print(
                f"  {item.op} {item.original_filename or item.item_id} "
                f"pages={len(item.page_indexes)} notebook={item.notebook_id}"
            )
        if args.dry_run:
            return 0
        run = orchestrator.create_run_from_plan(plan)
        completed = orchestrator.commit_run(run.import_run_id)
        print(f"import_run_id={completed.import_run_id} status={completed.status}")
        for item in completed.items:
            skip = f" skip={item.skip_classification}" if item.skip_classification else ""
            err = f" error={item.error_message}" if item.error_message else ""
            print(f"  {item.item_id} {item.state}{skip}{err}")
        return 0 if completed.status in {"complete", "partial"} else 1

    if args.bulk_cmd == "folders":
        policy = (
            POLICY_CREATE_DUPLICATE_V1
            if args.policy == "create_duplicate_v1"
            else POLICY_SKIP_EXISTING_V1
        )
        on_existing = args.on_existing
        plan, scan = plan_from_folders(
            args.parent,
            ids=ids,
            corpus_paths=corpus,
            import_policy_id=policy,
            on_existing=on_existing,
        )
        print(
            f"scan parent={scan.parent} new={len(scan.new_folders)} "
            f"already_imported={len(scan.already_imported)} "
            f"empty_skipped={len(scan.empty_skipped)} on_existing={on_existing}"
        )
        for conflict in scan.already_imported:
            print(
                f"  already_imported {conflict.managed_relpath} "
                f"notebook_id={conflict.notebook_id} title={conflict.title!r}"
            )
        for empty in scan.empty_skipped:
            print(f"  empty_skipped {empty.name}")
        print(
            f"plan_id={plan.plan_id} items={len(plan.items)} "
            f"policy={plan.import_policy_id} fingerprint={plan.fingerprint()[:12]}…"
        )
        notebooks: dict[str, list] = {}
        for item in plan.items:
            notebooks.setdefault(item.notebook_id, []).append(item)
        for nb_id, items in notebooks.items():
            title = (items[0].provenance or {}).get("title") or nb_id
            print(
                f"  notebook {title!r} id={nb_id} "
                f"sources={len(items)} pages={sum(len(i.page_indexes) for i in items)}"
            )
        if args.dry_run:
            return 0
        if on_existing == "overwrite" and scan.already_imported:
            prepare_folder_overwrite(
                scan.already_imported,
                corpus,
                confirm=args.confirm_overwrite or "",
                clock=clock,
            )
            print(f"overwrite wiped={len(scan.already_imported)} " f"managed notebook(s)")
        run = orchestrator.create_run_from_plan(plan)
        completed = orchestrator.commit_run(run.import_run_id)
        print(f"import_run_id={completed.import_run_id} status={completed.status}")
        for item in completed.items:
            skip = f" skip={item.skip_classification}" if item.skip_classification else ""
            err = f" error={item.error_message}" if item.error_message else ""
            print(f"  {item.item_id} {item.state}{skip}{err}")
        return 0 if completed.status in {"complete", "partial"} else 1

    if args.bulk_cmd == "status":
        run = ImportRunStore(corpus).load(args.import_run_id)
        print(
            f"import_run_id={run.import_run_id} status={run.status} "
            f"plan_id={run.plan_id} policy={run.import_policy_id}"
        )
        for item in run.items:
            skip = f" skip={item.skip_classification}" if item.skip_classification else ""
            err = f" error={item.error_message}" if item.error_message else ""
            print(f"  {item.item_id} {item.state}{skip}{err}")
        return 0

    if args.bulk_cmd == "resume":
        completed = orchestrator.commit_run(args.import_run_id)
        print(f"import_run_id={completed.import_run_id} status={completed.status}")
        for item in completed.items:
            print(f"  {item.item_id} {item.state}")
        return 0 if completed.status in {"complete", "partial"} else 1

    print(f"error: unknown bulk-import subcommand {args.bulk_cmd}", file=sys.stderr)
    return 2


def _cmd_bulk_run(args: argparse.Namespace, *, clock, ids) -> int:
    from transcribe.corpus.ocr_run import OcrBatchRunStore
    from transcribe.corpus.paths import CorpusPaths
    from transcribe.domain.models import OCRSettings
    from transcribe.providers.ollama import (
        OllamaVisionProvider,
        is_local_machine_host,
        normalize_base_url,
    )
    from transcribe.services.batch_ocr import (
        BatchOcrCoordinator,
        list_candidates,
        resolve_notebook_ref,
        select_by_ids,
        select_from_import_run,
        select_pending,
    )

    corpus = CorpusPaths.from_runtime(PATHS)
    coord = BatchOcrCoordinator(corpus, clock=clock, ids=ids)
    store = OcrBatchRunStore(corpus)

    if args.bulk_run_cmd == "status":
        run = store.load(args.ocr_run_id)
        models = (
            ",".join(run.vision_model_names)
            if run.mode == "multipass" and run.vision_model_names
            else (run.settings or {}).get("model_name", "")
        )
        print(
            f"ocr_run_id={run.ocr_run_id} status={run.status} mode={run.mode} "
            f"models={models} force={run.force} items={len(run.items)}"
        )
        if run.import_run_id:
            print(f"import_run_id={run.import_run_id}")
        for item in run.items:
            err = f" error={item.error_message}" if item.error_message else ""
            pass_bit = f" pass_id={item.pass_id}" if item.pass_id else ""
            print(
                f"  {item.notebook_id} {item.state} "
                f"pages={item.pages_completed}/{item.pages_total} "
                f"failed={item.pages_failed} skipped={item.pages_skipped}"
                f"{pass_bit}{err}"
            )
        return 0

    if args.bulk_run_cmd == "resume":
        progress = coord.resume(args.ocr_run_id, blocking=True)
        run = store.load(progress.ocr_run_id)
        print(f"ocr_run_id={run.ocr_run_id} status={run.status} mode={run.mode}")
        for item in run.items:
            print(f"  {item.notebook_id} {item.state}")
        return 0 if run.status in {"completed", "partial"} else 1

    url = normalize_base_url(args.base_url or default_ollama_base_url())
    if not is_local_machine_host(url) and not args.allow_remote_ollama:
        print(
            "Refusing non-local Ollama host without --allow-remote-ollama "
            "(page images would leave this machine).",
            file=sys.stderr,
        )
        return 2
    models = [m.strip() for m in (args.model or []) if m and str(m).strip()]
    if not models:
        print("error: at least one --model is required", file=sys.stderr)
        return 2
    is_multipass = len(models) >= 2
    if (args.cleanup_mode or args.cleanup_model) and not args.cleanup:
        print(
            "error: --cleanup-mode / --cleanup-model require --cleanup",
            file=sys.stderr,
        )
        return 2

    text_model = (args.text_model or "").strip()
    cleanup_model = (args.cleanup_model or "").strip() or text_model
    settings = OCRSettings(
        model_name=models[0],
        base_url=url,
        max_workers=max(1, min(2, args.workers)),
        allow_non_loopback=bool(args.allow_remote_ollama),
        cleanup_enabled=bool(args.cleanup) and not is_multipass,
        cleanup_mode=args.cleanup_mode or "strip_leak",
        cleanup_model_name=cleanup_model,
        text_model_name=text_model or cleanup_model,
        auto_activate_composite=not bool(getattr(args, "no_auto_composite", False)),
    )
    coord.provider = OllamaVisionProvider(url)
    candidates = list_candidates(corpus, clock=clock, ids=ids)
    import_run_id = None
    if args.bulk_run_cmd == "pending":
        selected = select_pending(candidates)
    elif args.bulk_run_cmd == "import-run":
        import_run_id = args.import_run_id
        selected = select_from_import_run(corpus, import_run_id, candidates)
    elif args.bulk_run_cmd == "notebooks":
        nids: list[str] = []
        for ref in args.notebooks:
            nid, _root = resolve_notebook_ref(corpus, ref)
            nids.append(nid)
        selected = select_by_ids(candidates, nids)
    else:
        print(
            f"error: unknown bulk-run subcommand {args.bulk_run_cmd}",
            file=sys.stderr,
        )
        return 2

    if not selected:
        print("No notebooks selected.")
        return 1
    try:
        run = coord.create_run(
            selected,
            settings=settings,
            force=bool(args.force),
            import_run_id=import_run_id,
            mode="multipass" if is_multipass else "single",
            vision_model_names=models if is_multipass else None,
            multipass_cleanup_enabled=bool(args.cleanup) if is_multipass else False,
        )
    except ValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    model_label = ",".join(models) if is_multipass else models[0]
    print(
        f"ocr_run_id={run.ocr_run_id} notebooks={len(run.items)} "
        f"mode={run.mode} models={model_label} force={run.force}"
    )
    progress = coord.run_blocking(run.ocr_run_id)
    finished = store.load(progress.ocr_run_id)
    print(f"status={finished.status}")
    for item in finished.items:
        err = f" error={item.error_message}" if item.error_message else ""
        print(f"  {item.notebook_id} {item.state}{err}")
    return 0 if finished.status in {"completed", "partial"} else 1


def _cmd_bulk_analyse(args: argparse.Namespace, *, clock, ids) -> int:
    from transcribe.analysis.presets import resolve_analysis_preset
    from transcribe.corpus.analysis_batch_run import AnalysisBatchRunStore
    from transcribe.corpus.paths import CorpusPaths
    from transcribe.services.batch_analysis import (
        BatchAnalysisCoordinator,
        list_analysis_candidates,
        select_by_ids,
        select_from_import_run,
        select_needing_analysis,
    )
    from transcribe.services.batch_notebooks import resolve_notebook_ref

    corpus = CorpusPaths.from_runtime(PATHS)
    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    store = AnalysisBatchRunStore(corpus)

    if args.bulk_analyse_cmd == "status":
        run = store.load(args.analysis_batch_id)
        print(
            f"analysis_batch_id={run.analysis_batch_id} status={run.status} "
            f"preset={run.preset_key or '-'} modules={len(run.module_ids)} "
            f"items={len(run.items)}"
        )
        if run.import_run_id:
            print(f"import_run_id={run.import_run_id}")
        for item in run.items:
            err = f" error={item.error_message}" if item.error_message else ""
            print(
                f"  {item.notebook_id} {item.state} "
                f"modules={item.modules_completed}/{item.modules_total} "
                f"failed={item.modules_failed} skipped={item.modules_skipped}{err}"
            )
        return 0

    if args.bulk_analyse_cmd == "resume":
        progress = coord.resume(args.analysis_batch_id, blocking=True)
        run = store.load(progress.analysis_batch_id)
        print(f"analysis_batch_id={run.analysis_batch_id} status={run.status}")
        for item in run.items:
            print(f"  {item.notebook_id} {item.state}")
        return 0 if run.status in {"completed", "partial"} else 1

    preset = str(args.preset or "balanced")
    custom = [m.strip() for m in (args.module or []) if m and str(m).strip()]
    if preset == "custom" and not custom:
        print("error: --preset custom requires at least one --module", file=sys.stderr)
        return 2
    resolved = resolve_analysis_preset(preset, custom_modules=custom)
    question = (args.question or "").strip() or None
    module_ids = list(resolved.module_ids)
    if question and "llm_custom_qa" not in module_ids:
        module_ids.append("llm_custom_qa")

    candidates = list_analysis_candidates(corpus, clock=clock, ids=ids)
    import_run_id = None
    if args.bulk_analyse_cmd == "pending":
        selected = select_needing_analysis(candidates)
    elif args.bulk_analyse_cmd == "import-run":
        import_run_id = args.import_run_id
        selected = select_from_import_run(corpus, import_run_id, candidates, purpose="analyse")
    elif args.bulk_analyse_cmd == "notebooks":
        nids: list[str] = []
        for ref in args.notebooks:
            nid, _root = resolve_notebook_ref(corpus, ref)
            nids.append(nid)
        selected = select_by_ids(candidates, nids)
    else:
        print(
            f"error: unknown bulk-analyse subcommand {args.bulk_analyse_cmd}",
            file=sys.stderr,
        )
        return 2

    if not selected:
        print("error: no notebooks selected", file=sys.stderr)
        return 2

    run = coord.create_run(
        selected,
        module_ids=module_ids,
        question_text=question,
        preset_label=preset.title(),
        preset_key=resolved.preset,
        preset_content_version=resolved.content_version,
        preset_policy_fingerprint=resolved.policy_fingerprint,
        import_run_id=import_run_id,
        text_model_name=(args.text_model or "").strip() or None,
    )
    print(
        f"analysis_batch_id={run.analysis_batch_id} notebooks={len(run.items)} "
        f"preset={run.preset_key} modules={len(run.module_ids)}"
    )
    progress = coord.run_blocking(run.analysis_batch_id)
    finished = store.load(progress.analysis_batch_id)
    print(f"status={finished.status}")
    for item in finished.items:
        err = f" error={item.error_message}" if item.error_message else ""
        print(f"  {item.notebook_id} {item.state}{err}")
    return 0 if finished.status in {"completed", "partial"} else 1


def _cmd_corpus_doctor(args: argparse.Namespace) -> int:
    from transcribe.corpus.paths import CorpusPaths
    from transcribe.services.corpus_doctor import CorpusDoctorService

    report = CorpusDoctorService(CorpusPaths.from_runtime(PATHS)).run(deep=args.deep)
    for finding in report.findings:
        print(f"{finding.severity}: [{finding.code}] {finding.message}")
    if report.ok and not report.findings:
        print("ok: corpus integrity checks passed")
    elif report.ok:
        print("ok: no errors (warnings above)")
    return 0 if report.ok else 1


def _cmd_backup(args: argparse.Namespace) -> int:
    from transcribe.errors import BackupError
    from transcribe.runtime_paths import build_runtime_paths
    from transcribe.services.workspace_backup import (
        BackupOptions,
        WorkspaceBackupService,
        default_backup_dest,
    )

    runtime = build_runtime_paths()
    service = WorkspaceBackupService()
    try:
        if args.backup_cmd == "create":
            dest = Path(args.dest) if args.dest else default_backup_dest(runtime)
            result = service.create_backup(
                runtime,
                dest,
                BackupOptions(
                    include_inbox=bool(args.include_inbox),
                    include_exports=bool(args.include_exports),
                ),
                force=bool(args.force),
            )
            print(f"wrote {result.archive_path}")
            print(
                f"notebooks={result.notebook_count} files={result.file_count} "
                f"uncompressed_bytes={result.uncompressed_bytes}"
            )
            includes = result.manifest.get("includes") or {}
            print(
                "includes: "
                + ", ".join(f"{key}={value}" for key, value in sorted(includes.items()))
            )
            return 0
        if args.backup_cmd == "verify":
            result = service.verify_backup(Path(args.archive))
            for message in result.messages:
                print(f"note: {message}")
            counts = (result.manifest.get("counts") or {}) if result.manifest else {}
            includes = (result.manifest.get("includes") or {}) if result.manifest else {}
            print(
                "ok: backup verified "
                f"(notebooks={counts.get('notebooks')} files={counts.get('files')} "
                f"uncompressed_bytes={counts.get('uncompressed_bytes')})"
            )
            if includes:
                print(
                    "includes: "
                    + ", ".join(f"{key}={value}" for key, value in sorted(includes.items()))
                )
            created = (result.manifest or {}).get("created_at")
            version = (result.manifest or {}).get("transcribe_version")
            if created or version:
                print(f"created_at={created} transcribe_version={version}")
            return 0
    except BackupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"error: unknown backup subcommand {args.backup_cmd!r}", file=sys.stderr)
    return 2


def _cmd_restore(args: argparse.Namespace) -> int:
    from transcribe.errors import BackupError
    from transcribe.runtime_paths import build_runtime_paths
    from transcribe.services.workspace_backup import WorkspaceBackupService

    runtime = build_runtime_paths()
    service = WorkspaceBackupService()
    archive = Path(args.archive)
    dry_run = bool(args.dry_run)
    if not dry_run and not args.yes:
        print(
            "Restore replaces notebooks, corpus, and config from the archive.\n"
            f"  archive: {archive}\n"
            f"  projects: {runtime.projects_dir}\n"
            f"  data: {runtime.data_dir}\n"
            "Re-run with --yes to confirm, or --dry-run to preview.",
            file=sys.stderr,
        )
        return 2
    try:
        result = service.restore_backup(
            runtime,
            archive,
            safety=not bool(args.no_safety_backup),
            dry_run=dry_run,
        )
    except BackupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for message in result.messages:
        print(message)
    if result.safety_archive is not None:
        print(f"safety_archive={result.safety_archive}")
    if result.doctor is not None:
        for finding in result.doctor.findings:
            print(f"{finding.severity}: [{finding.code}] {finding.message}")
        for nb_id, nb_report in result.doctor.notebook_reports.items():
            for finding in nb_report.findings:
                print(f"{finding.severity}: [{nb_id}/{finding.code}] {finding.message}")
    if dry_run:
        print("ok: dry-run complete (no changes)")
        return 0
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
