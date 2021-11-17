# MIT License
#
# Copyright (c) 2021 Dragorn421
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import pyrt


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import List, Optional

import struct


scene_table_entry_struct = struct.Struct(">IIIIBBBB")
assert scene_table_entry_struct.size == 0x14


class SceneTable:
    def __init__(self):
        self.scene_table = None  # type: List[SceneTableEntry]


class SceneTableEntry:
    def __init__(
        self,
        scene_file,  # type: pyrt.RomFile
        title_file,  # type: Optional[pyrt.RomFile]
        unk_10,
        config,
        unk_12,
        unk_13,
    ):
        self.scene_file = scene_file
        self.title_file = title_file
        self.unk_10 = unk_10
        self.config = config
        self.unk_12 = unk_12
        self.unk_13 = unk_13

    def __str__(self):
        return " ".join(
            (
                "Scene {0.scene_file.dma_entry}",
                "Title {0.title_file.dma_entry}" if self.title_file else "untitled",
                "{0.unk_10} {0.config:02} {0.unk_12} {0.unk_13}",
            )
        ).format(self)


def parse_scene_table(
    pyrti,  # type: pyrt.PyRTInterface
):
    rom = pyrti.rom

    scene_table_length = rom.version_info.scene_table_length

    scene_table = [None] * scene_table_length  # type: List[SceneTableEntry]
    for scene_id in range(scene_table_length):
        (
            scene_vrom_start,
            scene_vrom_end,
            title_vrom_start,
            title_vrom_end,
            unk_10,
            config,
            unk_12,
            unk_13,
        ) = scene_table_entry_struct.unpack_from(
            rom.file_code.data,
            rom.version_info.scene_table_code_offset
            + scene_id * scene_table_entry_struct.size,
        )
        assert scene_vrom_start <= scene_vrom_end
        assert title_vrom_start <= title_vrom_end

        scene_file = rom.find_file_by_vrom(scene_vrom_start)
        assert scene_file.dma_entry.vrom_start == scene_vrom_start
        assert scene_file.dma_entry.vrom_end == scene_vrom_end

        if title_vrom_start == 0 and title_vrom_end == 0:
            # untitled scene
            title_file = None
        else:
            # titled scene
            title_file = rom.find_file_by_vrom(title_vrom_start)
            assert title_file.dma_entry.vrom_start == title_vrom_start
            assert title_file.dma_entry.vrom_end == title_vrom_end

        scene_table_entry = SceneTableEntry(
            scene_file,
            title_file,
            unk_10,
            config,
            unk_12,
            unk_13,
        )

        scene_table[scene_id] = scene_table_entry

        scene_table_entry.scene_file.moveable_vrom = True
        if scene_table_entry.title_file is not None:
            scene_table_entry.title_file.moveable_vrom = True

        print(
            "{:03}".format(scene_id),
            scene_table_entry if scene_table_entry is not None else "-",
        )

    module_data = pyrti.modules_data[TASK]  # type: SceneTable
    module_data.scene_table = scene_table


def pack_scene_table(
    pyrti,  # type: pyrt.PyRTInterface
):
    module_data = pyrti.modules_data[TASK]  # type: SceneTable

    rom = pyrti.rom
    code_data = rom.file_code.data

    assert (
        len(module_data.scene_table)
        <= rom.version_info.scene_table_length
    )

    for scene_id, scene_table_entry in enumerate(module_data.scene_table):
        scene_vrom_start = scene_table_entry.scene_file.dma_entry.vrom_start
        scene_vrom_end = scene_table_entry.scene_file.dma_entry.vrom_end
        if scene_table_entry.title_file is not None:
            title_vrom_start = scene_table_entry.title_file.dma_entry.vrom_start
            title_vrom_end = scene_table_entry.title_file.dma_entry.vrom_end
        else:
            title_vrom_start = 0
            title_vrom_end = 0
        scene_table_entry_struct.pack_into(
            code_data,
            rom.version_info.scene_table_code_offset
            + scene_id * scene_table_entry_struct.size,
            scene_vrom_start,
            scene_vrom_end,
            title_vrom_start,
            title_vrom_end,
            scene_table_entry.unk_10,
            scene_table_entry.config,
            scene_table_entry.unk_12,
            scene_table_entry.unk_13,
        )


def register_pyrt_module(
    pyrti,  # type: pyrt.PyRTInterface
):
    pyrti.modules_data[TASK] = SceneTable()
    pyrti.add_event_listener(pyrt.EVENT_DMA_LOAD_DONE, parse_scene_table)
    pyrti.add_event_listener(pyrt.EVENT_ROM_VROM_REALLOC_DONE, pack_scene_table)


TASK = "scene table"

pyrt_module_info = pyrt.ModuleInfo(
    task=TASK,
    description="Handles parsing and packing the scene table.",
    register=register_pyrt_module,
)
