import logging
import re
from pathlib import Path
from typing import Optional

from maya import cmds

logger = logging.getLogger(__name__)


def get_references() -> list[str]:
    """
    Retrieve all the references nodes from scene.
    """

    def is_ref_valid(ref_name: str):
        return (
            "sharedReferenceNode" not in ref_name
            and "_UNKNOWN_REF_NODE_" not in ref_name
        )

    scene_reference_list = cmds.ls(type="reference", long=True)
    scene_reference_list = list(filter(is_ref_valid, scene_reference_list))
    return scene_reference_list


class RepathedReference:
    def __init__(self, node_name: str, previous_path: Path, new_path: Path):
        self.node_name: str = node_name
        self.previous_path: Path = previous_path
        self.new_path: Path = new_path

    def was_updated(self) -> bool:
        """
        True if the new path was different from the previous path.
        """
        return not self.previous_path == self.new_path


def repath_reference(
    node_name,
    search: str,
    replace: Path,
) -> Optional[RepathedReference]:
    """
    Given the reference node name, edit its path to an existing one, so it can be loaded.

    Args:
        node_name: existing maya node name
        search: part of the path to replace. A regex patterns.
        replace: partial part to swap with the result of the search

    Returns:
        result of the repathing as RepathedReference instance

    Raises:
        ValueError: cannot retrieve reference file path
        FileNotFoundError: new path computed doesn't exist on disk
    """
    # some references don't have filepath and might raise here
    current_path = cmds.referenceQuery(
        node_name,
        filename=True,
        withoutCopyNumber=True,
    )

    if not current_path:
        raise ValueError(f"Cannot retrieve reference file path on {node_name}")

    current_path = Path(current_path)
    logger.info(f"current_path={current_path}")

    search_pattern = re.compile(search)
    actual_search = search_pattern.match(str(current_path))
    if not actual_search:
        raise ValueError(
            f"Search pattern doesn't match anything: {search} on {current_path}>"
        )

    actual_search = actual_search.group(0)

    new_path = str(current_path).replace(actual_search, str(replace))
    new_path = Path(new_path)

    if not new_path.exists():
        raise FileNotFoundError(f"New path computed doesn't exist on disk: {new_path}")

    repathed_reference = RepathedReference(
        node_name,
        previous_path=current_path,
        new_path=new_path,
    )

    if not repathed_reference.was_updated():
        logger.info(f"Returning earlier, path is already up-to-date on <{node_name}>")
        return None

    logger.info(f"new_path={new_path}")

    logger.info(f"Repathing <{node_name}> ...")
    # a reference repath can fail because of unkown node, we usually want to ignore that
    # so that's why we just log the error and still consider the repathing sucessful.
    try:
        cmds.file(str(new_path), loadReference=node_name, loadReferenceDepth="none")
    except Exception as excp:
        logger.error(f"{excp}")

    return repathed_reference


def open_and_repath_references(
    maya_file_path: Path,
    search: str,
    replace: Path,
) -> list[RepathedReference]:
    """
    Open the given maya file and repath all the references inside.

    Args:
        maya_file_path:
        search: part of the path to replace. A regex patterns.
        replace: partial part to swap with the result of the search

    Returns:
        list of RepathedReference instances.
    """

    logger.info(f"Opening <{maya_file_path}> ...")
    try:
        # still trigger warning but doesn't load references
        cmds.file(
            maya_file_path,
            open=True,
            force=True,
            loadReferenceDepth="none",
            prompt=False,
        )
    except Exception as excp:
        logger.error(f"{excp}")

    scene_reference_list = get_references()
    if not scene_reference_list:
        logger.info("Returned early: no references in scene.")
        return []

    repathed_reference_list = []

    for index, scene_reference in enumerate(scene_reference_list):

        logger.info(
            f"{index+1}/{len(scene_reference_list)} Repathing {scene_reference} ..."
        )
        try:
            repathed_reference = repath_reference(
                node_name=scene_reference,
                search=search,
                replace=replace,
            )
        except Exception as excp:
            logger.error(excp)
            repathed_reference = None

        if repathed_reference:
            repathed_reference_list.append(repathed_reference)

    logger.info(f"Finished.")
    return repathed_reference_list
