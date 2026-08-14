---
name: unity-performance-optimization
description: Measure and improve Unity performance through Unity MCP. Use for CPU or GPU frame-time spikes, garbage collection, memory growth or leaks, draw calls, batches, overdraw, physics cost, asset memory, loading or runtime hitches, mobile or XR budgets, Profiler captures, Memory Profiler snapshots, Frame Debugger analysis, rendering statistics, and evidence-based optimization or performance regression work.
---

# Unity Performance Optimization

Optimize only after establishing a repeatable workload, target hardware or platform, and before/after measurements.

## Measurement Workflow

1. Record target platform, frame-rate/frame-time budget, representative scene, quality level, resolution, and reproduction window.
2. Read editor/project state and pipeline information. Prefer profiling a development player for shipping conclusions; label Editor-only measurements.
3. Establish a baseline with `mcp__unity__manage_profiler(action="get_frame_timing")`, category counters, rendering stats, and memory stats.
4. Start a bounded profiler capture with only relevant areas. Enable allocation call stacks only when necessary because they add overhead.
5. Route by evidence:
   - CPU/scripts: inspect main-thread and script counters, allocations, update frequency, and expensive searches.
   - GPU/rendering: inspect draw calls, batches, triangles, Frame Debugger events, shadows, post effects, transparency, and resolution.
   - Memory: inspect object memory; take and compare Memory Profiler snapshots when the package is available.
   - Physics: inspect fixed timestep, bodies, colliders, layers, queries, and validation.
   - Assets/loading: inspect texture/model/audio import settings, duplicate assets, and lifecycle.
6. Change one bottleneck class at a time and keep visual/gameplay behavior constant.
7. Repeat the same capture, compare metrics, and retain only changes with a meaningful verified gain.

## Optimization Rules

- Report milliseconds and memory, not only percentages.
- Separate CPU and GPU bottlenecks; lowering draw calls will not fix a script-bound frame.
- Do not trade correctness, determinism, accessibility, or visible quality without user agreement.
- Avoid micro-optimizing cold paths while a measured hot path dominates.
- Keep platform constraints explicit; desktop Editor results do not prove mobile performance.
- Use object pooling only when allocation/lifecycle measurements justify the complexity.
- Check build configuration, deep profiling, VSync, target frame rate, and development flags before comparing captures.

## Completion Gate

Provide the baseline, changed variables, after metrics under the same workload, percentage and absolute improvement, regressions checked, and any remaining bottleneck. Do not claim improvement without comparable measurements.

Read the shared [tool reference](../unity-mcp-skill/references/tools-reference.md) for profiler and graphics actions.
