# Maya Asset Validator & Batch Exporter

A Python tool for checking selected static mesh assets in Autodesk Maya and exporting each eligible asset to an individual FBX file. Built to reduce repetitive export steps and provide clear, actionable feedback before an asset handoff.

**Developer:** Siddharth Dixit  
**Version:** 1.0

**Demo:**  https://youtu.be/kMkgAXHOxt4 
**Portfolio:** https://siddharthdixit.artstation.com/

## Overview

When exporting multiple props, artists may need to repeat selection, filename entry, export settings and checks for every asset. This tool captures an asset selection, checks common handoff requirements, and exports eligible meshes using consistent settings.

The interface separates **Selection Checks**, **Asset Export Checks and Outcomes**, and **Batch Updates**. Clicking an asset-related result displays its details and selects the corresponding object in Maya.

## Features

- Collect mesh transforms or resolve directly selected mesh shapes to their transforms.
- Reject components, groups without direct mesh geometry, cameras, lights, curves and intermediate mesh shapes.
- Preserve asset order while removing duplicate transform entries.
- Validate output filenames against common Windows restrictions, including namespace colons and reserved device names.
- Detect case-insensitive filename collisions between assets in the batch.
- Check for an existing output destination before exporting; skip rather than intentionally overwrite it.
- Report non-default local translation, rotation and scale as warnings without changing the asset.
- Check for UV coordinates in a user-specified UV set, such as `map1` or `UVMap`.
- Export one FBX per eligible transform, preserving filename capitalization.
- Choose partial-batch or strict-batch behavior.
- Display colored results, select affected objects, and save results as JSON.
- Restore Maya selection and attempt to restore FBX settings after the batch.

## Requirements

- Autodesk Maya with Python 3 and the `fbxmaya` plugin available. The tool loads the plugin when export begins.
- No additional Python packages are required inside Maya.
- Existing output folder with write access.

**Tested Maya version:** Maya 2025
**Tested operating system:** Microsoft Windows Version 25H2 (OS Build 26200.9711)

Compatibility with other Maya versions and platforms has not been established. Filename validation currently follows Windows naming restrictions.

## Installation and launch

Ensure the script is named `maya_asset_exporter.py`.

### Run from the Script Editor

1. Open Maya's Script Editor and select a **Python** tab.
2. Open `maya_asset_exporter.py` or paste its full contents into the tab.
3. Execute the entire script. The tool window opens; no assets export until you click **Export**.

### Import from Maya's scripts folder

Place `maya_asset_exporter.py` in your Maya user scripts folder, then run:

```python
import maya_asset_exporter
maya_asset_exporter.show()
```

After editing an imported module, reload it before reopening the tool:

```python
import importlib
import maya_asset_exporter
importlib.reload(maya_asset_exporter)
maya_asset_exporter.show()
```

## Workflow

1. Select the static mesh objects you want to export.
2. Open the tool or click **Refresh Selection from Maya** to capture that selection.
3. Click **Browse** to choose an existing output folder.
4. Enter the UV set to check. The default is `map1`; imported assets may use a different name, such as `UVMap`.
5. Click **Validate** and review the three result panels.
6. Click an asset-related result to select the affected object and read the full explanation.
7. Correct errors, then validate again. After renaming, reparenting or changing your batch, click **Refresh Selection** to capture the updated paths.
8. Click **Export**. The tool revalidates the captured selection before exporting.
9. Review outcomes and optionally save a JSON report.

Selecting an object by clicking a result does **not** replace the captured export list. Use **Refresh Selection** explicitly when you want to change the batch. Export restores the Maya selection that was active when the export operation began.

Changing the required UV-set field only changes which set is checked; the tool does not create, rename or modify UV sets.

## Validation rules

| Check | Pass condition | Blocking behavior |
|---|---|---|
| Selection | Whole mesh transform or directly selected non-intermediate mesh shape | Unsupported selection items are skipped; strict mode blocks the batch |
| Output folder | Nonempty path to an existing directory | Error blocks the entire batch |
| UV-set field | A nonempty UV-set name | Error blocks the entire batch |
| Filename | Short transform name satisfies the implemented Windows filename rules | Error blocks the affected asset |
| Duplicate filename | No other batch asset maps to the same filename, ignoring case | All conflicting assets are blocked |
| Transforms | Local translation/rotation are zero and scale is one, within a tolerance of `0.00001` | Non-default values generate a warning and still allow export |
| UVs | Every direct non-intermediate mesh shape has the requested UV set with at least one UV coordinate | Error blocks the affected asset |
| Existing destination | Intended output path does not already exist | Existing destination is skipped |

An asset may have several result records: one for each check, and potentially several UV results if it has multiple mesh shapes. A failed prerequisite can prevent a later check from running.

### What the checks do not establish

- UV presence does not prove complete face assignment, a good unwrap, nonoverlapping shells or suitable texel density.
- Default local transforms do not prove geometry is centered at the world origin. Parent transforms, pivots, shear and world placement are not checked.
- A valid folder can still fail at export time because of permissions, disk space or other filesystem problems.

## Naming

Output filenames use the short transform name, while full DAG paths identify scene objects:

|DungeonGroup|WallGroup|Wall1  ->  Wall1.fbx


Different full DAG paths can share a short name, so these conflict:

|Barrel1  ->  Barrel1.fbx
|BarrelGroup|Barrel1 ->  Barrel1.fbx


Names differing only in case also conflict within the batch. Namespace colons are rejected rather than silently removed. `COM` is valid; `CON`, `NUL`, `COM1` and the other implemented device names are reserved.

## Batch policies

### Default: export eligible assets

Assets with blocking errors are skipped, while eligible assets export. Warnings do not block export. An individual runtime export failure is recorded and the batch continues.

### Strict: require all selected items to pass

Any preflight error blocks the entire batch. Warnings are allowed. If an export fails after the batch has started, remaining exports stop.

**Strict mode is not transactional:** it does not remove files already exported before a runtime failure.

Batch-wide problems, such as an invalid output folder, block all exports in either mode.

## Interface

| Area | Purpose |
|---|---|
| Captured selection | Shows the scene paths captured for the batch |
| Selection Checks | Shows supported and rejected selection items |
| Asset Export Checks and Outcomes | Shows per-asset validation and exported, skipped or failed outcomes |
| Batch Updates | Shows folder issues, validation summaries and batch completion/blocking messages |
| Selected Result Details | Shows the full clicked result, including its asset path and explanation |

Green indicates passes or successful exports, yellow indicates warnings or skipped exports, red indicates errors or failures, and blue indicates informational batch updates. The problems-only filter applies to the asset result panels; batch updates remain visible.

## Export behavior and limitations

- Static mesh handoffs only. This is not a rig, animation, skin, blendshape or simulation-cache publisher.
- Each export includes the selected transform's mesh geometry. Child transform hierarchies and automatic related input connections are disabled in the export settings.
- Smoothing groups and embedded textures are enabled; cameras, lights, skins and blendshapes are disabled. Animation baking is disabled. Material/texture transfer fidelity is not guaranteed.
- The tool does not automatically fix UVs, freeze transforms, rename objects or recenter geometry.
- Existing destination checks prevent intentional overwrites, but are not an atomic lock against other software writing to the same path concurrently.
- A failed export may leave a partial file. Inspect it before retrying.
- A nonempty output file is checked after export; reimporting and inspecting the FBX is still necessary to verify its contents.
- The tool does not manage asset versions, dependencies, scene assembly or coordinated publishing.
- Reports describe the last validation/export operation. Export revalidates, but displayed results can become stale after scene edits.

## Demonstration scene

The demonstration uses a modular dungeon with wall pieces, floor pieces, crates, barrels and torches. It illustrates individual FBX exports alongside selected-light rejection, duplicate filenames, missing UV data, transform warnings and existing-file protection. The required UV-set field can be changed from `map1` to `UVMap` for the imported assets.

## Suggested verification

Before using the tool for an asset delivery, test it with:

- Multiple valid meshes and direct shape selections.
- Components, groups, cameras and lights.
- Duplicate short names under different parents and names differing only in case.
- Missing UV sets, empty UV sets and non-default transforms.
- Existing destinations, paths containing spaces and an invalid folder.
- Partial and strict batch policies, including a forced export failure.
- Selection/settings restoration and JSON report saving.
- Reimported FBXs to confirm geometry, UVs and unintended-child exclusion.

## Development

Developed by **Siddharth Dixit** as a technical-art portfolio project exploring Maya scripting, artist-facing validation, UI design and batch export workflows. AI assistance was used during implementation and debugging.

## Feedback

To report a bug, include your Maya version, operating system, reproduction steps, relevant error output and a minimal example when possible.
