"""Maya Asset Validator & Batch Exporter, v1.0.
Static meshes only. Run show() in Maya's Python Script Editor.
"""
from pathlib import Path
import json
import math
import maya.cmds as cmds
import maya.mel as mel


def result(asset, check, severity, message):
    return dict(asset=asset, check=check, severity=severity, message=message)


def validate_asset_name(name):
    issues = []
    if not name:
        return ['Asset name is empty.']
    forbidden = set('<>:"/\\|?*')
    invalid_characters =  sorted({char for char in name if char in forbidden}) #sorted(set(name) & set('<>:"/\\|?*'))
    if invalid_characters:
        issues.append(f"Forbidden filename characters: {invalid_characters!r}")
    if any(ord(c) < 32 for c in name):
        issues.append('Name contains control characters.')
    if name.endswith((' ', '.')):
        issues.append('Name ends with a space or period.')
    reserved = {'CON', 'PRN', 'AUX', 'NUL'}
    reserved.update(prefix + digit for prefix in ('COM', 'LPT') for digit in '123456789¹²³')
    if name.split('.')[0].rstrip(' ').upper() in reserved:
        issues.append('Windows reserved device name.')
    return issues


def mesh_shapes(asset):
    return [s for s in (cmds.listRelatives(asset, shapes=True, noIntermediate=True, fullPath=True) or []) if cmds.nodeType(s) == 'mesh']


def collect_selected_meshes(selection):
    assets, rows = [], []
    for item in selection:
        try:
            if '.' in item:
                raise ValueError('Components are unsupported; select the object in Object Mode.')
            if not cmds.objExists(item):
                raise ValueError('Object no longer exists. Refresh Selection.')
            kind = cmds.nodeType(item)
            if kind == 'mesh':
                if cmds.getAttr(item + '.intermediateObject'):
                    raise ValueError('Intermediate mesh shapes are unsupported.')
                parents = cmds.listRelatives(item, parent=True, fullPath=True) or []
                if not parents or cmds.nodeType(parents[0]) != 'transform':
                    raise ValueError('Mesh has no supported transform parent.')
                asset = parents[0]
            elif kind == 'transform' and mesh_shapes(item):
                asset = item
            else:
                raise ValueError('Select a polygon mesh directly; groups, cameras, lights and curves are unsupported.')
            if asset not in assets:
                assets.append(asset)
                rows.append(result(asset, 'Selection', 'Pass', 'Supported mesh transform.'))
        except Exception as error:
            rows.append(result(item, 'Selection', 'Error', str(error)))
    if not selection:
        rows.append(result(None, 'Selection', 'Error', 'Select meshes, then click Refresh Selection.'))
    return assets, rows


def validate_batch(selection, folder, uv_set='map1'):
    """Read-only preflight. Returns validation rows and eligible export plan."""
    assets, rows = collect_selected_meshes(selection)
    folder_path = None
    
    #This section validates the output folder path
    try:
        if not folder.strip():
            raise ValueError('Choose an output folder.')
        folder_path = Path(folder).expanduser()
        if not folder_path.is_dir():
            raise ValueError('Output folder does not exist or is not a directory.')
        rows.append(result(None, 'Output Folder', 'Pass', str(folder_path)))
    except Exception as error:
        folder_path = None
        rows.append(result(None, 'Output Folder', 'Error', str(error)))
        
    #This section validates UV set of assets
    if not uv_set.strip():
        rows.append(result(None, 'UV Set', 'Error', 'Enter the UV set name to check.'))
        
    #Create a dictionary to store multiple assets with same name
    by_name = {}
    for asset in assets:
        by_name.setdefault((asset.split('|')[-1] + '.fbx').casefold(), []).append(asset)
    
    
    plan = []
    for asset in assets:
        name = asset.split('|')[-1]
        filename = name + '.fbx'
        start = len(rows)
        issues = validate_asset_name(name)
        
        #Identify name issues
        for issue in issues:
            rows.append(result(asset, 'Filename', 'Error', issue))
        if not issues:
            rows.append(result(asset, 'Filename', 'Pass', 'Valid filename: ' + filename))
        
        #Identify duplicate name conflicts
        conflicts = by_name[filename.casefold()]
        rows.append(result(asset, 'Duplicate Name', 'Error' if len(conflicts) > 1 else 'Pass',
                           'Conflicting outputs: ' + ', '.join(conflicts) if len(conflicts) > 1
                           else 'Filename is unique within this batch.'))
                           
        #Identify transform issues
        try:
            changed = []
            for attr, expected in (('translate', 0.0), ('rotate', 0.0), ('scale', 1.0)):
                values = cmds.getAttr(asset + '.' + attr)[0]
                if any(not math.isclose(v, expected, rel_tol=0.0, abs_tol=1e-5) for v in values):
                    changed.append('{}={}'.format(attr, tuple(round(v, 5) for v in values)))
            rows.append(result(asset, 'Transforms', 'Warning' if changed else 'Pass',
                               '; '.join(changed) + '. Review; no automatic freeze.' if changed
                               else 'Local translate/rotate/scale are default.'))
        except Exception as error:
            rows.append(result(asset, 'Transforms', 'Error', str(error)))
        
        #Identify UV issues
        try:
            shapes = mesh_shapes(asset)
            if not shapes:
                raise ValueError('No non-intermediate mesh shapes remain.')
            for shape in shapes:
                sets = cmds.polyUVSet(shape, query=True, allUVSets=True) or []
                if uv_set not in sets:
                    rows.append(result(asset, 'UVs', 'Error', '{}: UV set {!r} is missing.'.format(shape, uv_set)))
                else:
                    count = cmds.polyEvaluate(shape, uvcoord=True, uvSetName=uv_set) or 0
                    rows.append(result(asset, 'UVs', 'Pass' if count > 0 else 'Error',
                                       '{}: {} UV coordinates in {!r}. Presence only; not coverage or quality.'.format(shape, count, uv_set)))
        except Exception as error:
            rows.append(result(asset, 'UVs', 'Error', str(error)))
            
        #Identify files of same name alredy existing in destination folder
        path = folder_path / filename if folder_path is not None and not issues else None
        if path is not None:
            try:
                exists = path.exists()
                rows.append(result(asset, 'Existing File', 'Error' if exists else 'Pass',
                                   'Destination already exists: ' + str(path) if exists else 'Destination is available: ' + str(path)))
            except OSError as error:
                rows.append(result(asset, 'Existing File', 'Error', str(error)))
                
        #Assets validated for export
        if path is not None and not any(r['severity'] == 'Error' for r in rows[start:]):
            plan.append((asset, path))
    
    #Blocks export for all asssets for block wide errors
    if any(r['asset'] is None and r['severity'] == 'Error' for r in rows):
        plan = []
    return rows, plan


def export_fbx_with_settings(object_name, output_path):
    cmds.select(object_name, replace=True, noExpand=True)
    mel.eval('FBXResetExport;')
    settings = {
        'FBXExportSmoothingGroups': True,
        'FBXExportIncludeChildren': False,
        'FBXExportInputConnections': False,
        'FBXExportBakeComplexAnimation': False,
        'FBXExportAnimationOnly': False,
        'FBXExportSkins': False,
        'FBXExportShapes': False,
        'FBXExportCameras': False,
        'FBXExportLights': False,
        'FBXExportEmbeddedTextures': True,
    }
    for command, enabled in settings.items():
        mel.eval('{} -v {};'.format(command, 'true' if enabled else 'false'))
    path = Path(output_path).as_posix().replace('"', '\\"')
    mel.eval('FBXExport -f "{}" -s;'.format(path))
    if not Path(output_path).is_file() or Path(output_path).stat().st_size == 0:
        raise RuntimeError('Exporter returned without creating a nonempty FBX file.')


def export_batch(plan, strict=False):
    """Per-file outcomes; strict stops on first runtime failure, without rollback."""
    outcomes = []
    saved = cmds.ls(selection=True, long=True) or []
    settings_pushed = False
    try:
        if not cmds.pluginInfo('fbxmaya', query=True, loaded=True):
            cmds.loadPlugin('fbxmaya')
        # Preserve FBX options changed by the tool.
        mel.eval('FBXPushSettings;')
        settings_pushed = True
        stopped = False
        for asset, path in plan:
            if stopped:
                outcomes.append(dict(asset=asset, status='Skipped', message='Stopped after an earlier failure.'))
                continue
            try:
                if path.exists():
                    raise RuntimeError('Destination appeared after validation; overwrite prevented.')
                export_fbx_with_settings(asset, path)
            except Exception as error:
                outcomes.append(dict(asset=asset, status='Failed', message='{} (Inspect destination for a partial file.)'.format(error)))
                stopped = strict
            else:
                outcomes.append(dict(asset=asset, status='Exported', message=str(path)))
    except Exception as error:
        done = {r['asset'] for r in outcomes}
        outcomes.extend(dict(asset=a, status='Skipped', message='FBX setup failed: ' + str(error))
                        for a, p in plan if a not in done)
    finally:
        try:
            if settings_pushed:
                mel.eval('FBXPopSettings;')
        except Exception as error:
            cmds.warning('Could not restore FBX settings: ' + str(error))
        finally:
            remaining = [s for s in saved if cmds.objExists(s)]
            if remaining:
                cmds.select(remaining, replace=True, noExpand=True)
            else:
                cmds.select(clear=True)
    return outcomes



class AssetExporterUI:
    WINDOW = "mayaAssetValidatorBatchExporter"

    def __init__(self):
        self.selection = []
        self.rows = []
        self.outcomes = []
        self.selection_rows = []
        self.asset_rows = []
        self.batch_rows = []
        self.batch_updates = []

    def show(self):
        if cmds.window(self.WINDOW, exists=True):
            cmds.deleteUI(self.WINDOW)

        window = cmds.window(self.WINDOW, title="Asset Validator & Batch Exporter | v1.0", widthHeight=(840, 1000))

        cmds.scrollLayout(childResizable=True)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=7)
        
        cmds.text(label="Select. Validate. Export. Voila!", align="left")
        cmds.button(label="1. Refresh Selection from Maya", command=self.refresh)
        
        cmds.text(label="Selection Box", align="left")
        self.asset_list = cmds.textScrollList(height=80, allowMultiSelection=True, selectCommand=self.select_asset)
        cmds.text(label="Toggle through objects in Selection Box to modify your selection. 'Press Refresh Selection from Maya' to update.\n", align="left")
        
        self.folder = cmds.textFieldButtonGrp(label="Output folder", buttonLabel="Browse", buttonCommand=self.browse)
        self.uv = cmds.textFieldGrp(label="Required UV set", text="map1")
        
        cmds.text(label="The tool only checks presence of Required UV set. It does not check UV assignment, overlaps, seams, texel density, etc.\nDefault UV set is map1 but it can be changed based on requirement.\n", align="left")
        
        self.strict = cmds.checkBox(label='STRICT MODE: Blocks batch export if any asset remains unvalidated. "We Don\'t Leave A Soldier Behind!"', value=False)
        #cmds.text(label="Check the above box if you.\n"), align="left"

        cmds.rowLayout(numberOfColumns=2)
        cmds.button(label="2. Validate", width=380, backgroundColor=(0.25, 0.45, 0.65), command=self.validate)
        cmds.button(label="3. Export", width=380, backgroundColor=(0.25, 0.55, 0.35), command=self.export)
        cmds.setParent("..")

        self.summary = cmds.text(label="\nRefresh Selection to begin.", align="left")
        self.problems = cmds.checkBox(label="BAD NEWS ONLY: Only show Warnings/Errors and unsuccessful exports", value=False, changeCommand=self.render)

        cmds.text(label="\nSelection Checks", align="left")
        self.selection_list = cmds.iconTextScrollList(height=100, allowMultiSelection=False, selectCommand=lambda *_: self.select_result_from(self.selection_list, self.selection_rows))

        cmds.text(label="Asset Export Checks and Outcomes", align="left")
        self.asset_results_list = cmds.iconTextScrollList(height=100, allowMultiSelection=False, selectCommand=lambda *_: self.select_result_from(self.asset_results_list, self.asset_rows))

        cmds.text(label="Batch Updates", align="left")
        self.batch_list = cmds.iconTextScrollList(height=50, allowMultiSelection=False, selectCommand=lambda *_: self.select_result_from(self.batch_list, self.batch_rows))

        cmds.text(label="Selected Result Details", align="left")
        self.detail = cmds.scrollField(editable=False, wordWrap=True, height=80, text="Click a result to view its details.")

        cmds.button(label="Save results as JSON...", command=self.save_report)

        cmds.showWindow(window)
        self.refresh()
        return self

    def refresh(self, *_):
        self.selection = cmds.ls(selection=True, long=True) or []
        assets, self.rows = collect_selected_meshes(self.selection)
        self.outcomes = []
        self.batch_updates = []

        cmds.textScrollList(self.asset_list, edit=True, removeAll=True)

        if self.selection:
            cmds.textScrollList(self.asset_list, edit=True, append=self.selection)

        message = f"\n{len(assets)} supported mesh asset(s) in selection. Click Validate to inspect the selection.\n"
        self.batch_updates.append(result(None, "Selection Refresh", "Info", message))

        cmds.text(self.summary, edit=True, label=message)
        self.render()

    def browse(self, *_):
        paths = cmds.fileDialog2(fileMode=3, dialogStyle=2, caption="Select Output Folder")

        if not paths:
            self.batch_updates.append(result(None, "Output Folder", "Info", "Folder selection cancelled. Previous folder remains unchanged."))
            self.render()
            return

        cmds.textFieldButtonGrp(self.folder, edit=True, text=paths[0])

        # Remove stale validation and export outcomes after changing the folder.
        assets, self.rows = collect_selected_meshes(self.selection)
        self.outcomes = []
        self.batch_updates = [result(None, "Output Folder", "Info", f"Folder changed to: {paths[0]}. Validate again before reviewing results.")]

        cmds.text(self.summary, edit=True, label="Folder changed. Click Validate or Export to recheck.")
        self.render()

    def validate(self, *_):
        folder = cmds.textFieldButtonGrp(self.folder, query=True, text=True)
        uv_set = cmds.textFieldGrp(self.uv, query=True, text=True).strip()

        self.rows, plan = validate_batch(self.selection, folder, uv_set)
        self.outcomes = []
        self.batch_updates = []

        errors = sum(row["severity"] == "Error" for row in self.rows)
        warnings = sum(row["severity"] == "Warning" for row in self.rows)

        message = f"{len(plan)} ready | {errors} error(s) | {warnings} warning(s)"
        severity = "Error" if errors else "Warning" if warnings else "Pass"

        self.batch_updates.append(result(None, "Validation Summary", severity, message))
        cmds.text(self.summary, edit=True, label=message)

        self.render()
        return plan

    def export(self, *_):
        # Always revalidate current scene properties before exporting.
        plan = self.validate()

        strict = cmds.checkBox(self.strict, query=True, value=True)
        has_errors = any(row["severity"] == "Error" for row in self.rows)
        batch_error = any(row["asset"] is None and row["severity"] == "Error" for row in self.rows)
        blocked = batch_error or (strict and has_errors)

        ready = {asset for asset, path in plan}
        assets = list(dict.fromkeys(row["asset"] for row in self.rows if row["asset"] is not None))

        if batch_error:
            blocked_reason = "Batch error. Check for missing folder path or missing UV set. Resolve the errors in Batch Updates."
        elif blocked:
            blocked_reason = "STRICT MODE ON! Blocked the batch because validation errors exist."
        else:
            blocked_reason = "Asset blocked by validation. See its error results."

        for asset in assets:
            if blocked or asset not in ready:
                self.outcomes.append(dict(asset=asset, status="Skipped", message=blocked_reason))

        if not blocked and plan:
            self.outcomes.extend(export_batch(plan, strict))

        exported = sum(row["status"] == "Exported" for row in self.outcomes)
        failed = sum(row["status"] == "Failed" for row in self.outcomes)
        skipped = sum(row["status"] == "Skipped" for row in self.outcomes)

        counts = f"\n{exported} exported | {failed} failed | {skipped} skipped"

        if blocked:
            message = f"Export blocked. {blocked_reason} {counts}"
            severity = "Error"
        elif not plan:
            message = f"No eligible assets to export. {counts}"
            severity = "Warning"
        elif failed:
            message = f"Export finished with failures. {counts}"
            severity = "Error"
        elif skipped:
            message = f"Export finished with skipped assets. {counts}"
            severity = "Pass"
        else:
            message = f"Export complete. {counts}"
            severity = "Pass"

        self.batch_updates.append(result(None, "Export Summary", severity, message))
        cmds.text(self.summary, edit=True, label=message)

        self.render()

    def render(self, *_):
        only_problems = cmds.checkBox(self.problems, query=True, value=True)

        selection_records = [row for row in self.rows if row["asset"] is not None and row["check"] == "Selection"]
        asset_records = [row for row in self.rows if row["asset"] is not None and row["check"] != "Selection"]

        # Individual export outcomes appear with the asset export checks.
        asset_records.extend(self.outcomes)

        self.selection_rows = [row for row in selection_records if not only_problems or row["severity"] != "Pass"]
        self.asset_rows = [row for row in asset_records if not only_problems or row.get("severity", row.get("status")) not in ("Pass", "Exported")]

        # Batch messages stay visible regardless of the filter.
        self.batch_rows = [row for row in self.rows if row["asset"] is None]
        self.batch_rows.extend(self.batch_updates)

        self.populate_results(self.selection_list, self.selection_rows)
        self.populate_results(self.asset_results_list, self.asset_rows)
        self.populate_results(self.batch_list, self.batch_rows)

        cmds.scrollField(self.detail, edit=True, text="Click a result for details. Export always revalidates the captured asset list.")

    def populate_results(self, control, displayed_rows):
        colors = {"Pass": (0.35, 0.85, 0.40), "Warning": (1.00, 0.85, 0.20), "Error": (1.00, 0.30, 0.30), "Exported": (0.35, 0.85, 0.40), "Failed": (1.00, 0.30, 0.30), "Skipped": (1.00, 0.85, 0.20), "Info": (0.65, 0.80, 1.00)}

        cmds.iconTextScrollList(control, edit=True, removeAll=True)

        for index, row in enumerate(displayed_rows, start=1):
            status = row.get("severity", row.get("status", "Info"))
            asset = row["asset"] or "Batch"
            check = row.get("check", "Export")
            message = row["message"]

            label = f"{index:03d} [{status}] {asset} | {check} | {message}".replace("\n", " ")
            color = colors.get(status, (0.85, 0.85, 0.85))

            cmds.iconTextScrollList(control, edit=True, append=label)
            cmds.iconTextScrollList(control, edit=True, itemTextColor=(index, *color))

    def select_asset(self, *_):
        indices = cmds.textScrollList(self.asset_list, query=True, selectIndexedItem=True) or []
        items = [self.selection[index - 1] for index in indices]
        valid = [item for item in items if cmds.objExists(item)]

        if valid:
            cmds.select(valid, replace=True, noExpand=True)

    def select_result_from(self, control, displayed_rows):
        indices = cmds.iconTextScrollList(control, query=True, selectIndexedItem=True) or []

        if not indices:
            return

        index = indices[0] - 1

        if index < 0 or index >= len(displayed_rows):
            return

        row = displayed_rows[index]
        details = "\n".join(f"{key}: {value}" for key, value in row.items())

        cmds.scrollField(self.detail, edit=True, text=details)

        if row["asset"]:
            if cmds.objExists(row["asset"]):
                cmds.select(row["asset"], replace=True, noExpand=True)
            else:
                cmds.scrollField(self.detail, edit=True, text=details + "\n\nObject no longer exists at this path. Refresh Selection.")

    def save_report(self, *_):
        paths = cmds.fileDialog2(fileMode=0, fileFilter="JSON (*.json)", caption="Save Results Report")

        if not paths:
            return

        try:
            report = dict(validation=self.rows, exports=self.outcomes, batch_updates=self.batch_updates)

            with open(paths[0], "w", encoding="utf-8") as stream:
                json.dump(report, stream, indent=2, ensure_ascii=False)

        except Exception as error:
            message = f"Could not save report: {error}"
            self.batch_updates.append(result(None, "Report", "Error", message))
            cmds.warning(message)
        else:
            self.batch_updates.append(result(None, "Report", "Info", f"Results saved to: {paths[0]}"))

        self.render()


def show():
    global _asset_exporter_ui
    _asset_exporter_ui = AssetExporterUI().show()
    return _asset_exporter_ui


if __name__ == '__main__':
    show()

