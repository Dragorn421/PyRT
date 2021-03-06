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
    from typing import List, Optional, Dict

import struct
import codecs


actor_overlay_struct = struct.Struct(">IIIIIIIHbx")
assert actor_overlay_struct.size == 0x20


class ActorOverlayTable:
    def __init__(self):
        self.actor_overlay_table = None  # type: List[Optional[ActorOverlay]]
        self.names_vram_start = dict()  # type: Dict[str, int]


class ActorOverlay:
    def __init__(
        self,
        file,  # type: Optional[pyrt.RomFile]
        vram_start,
        vram_end,
        actor_init_vram_start,
        name,
        alloc_type,
    ):
        self.file = file
        self.vram_start = vram_start
        self.vram_end = vram_end
        self.actor_init_vram_start = actor_init_vram_start
        self.name = name
        self.alloc_type = alloc_type

    def __str__(self):
        return " ".join(
            (
                "{0.file.dma_entry}" if self.file else "internal",
                "VRAM 0x{0.vram_start:08X}-0x{0.vram_end:08X}",
                "init 0x{0.actor_init_vram_start:08X}",
                "alloc {0.alloc_type}",
                self.name,
            )
        ).format(self)


def parse_actor_overlay_table(
    pyrti,  # type: pyrt.PyRTInterface
):
    log = pyrti.logging_helper.get_logger(__name__)

    rom = pyrti.rom

    name_code_offset_ranges = []

    log.info("Parsing the actor overlay table...")

    actor_overlay_table_length = rom.version_info.actor_overlay_table_length
    actor_overlay_table = [
        None
    ] * actor_overlay_table_length  # type: List[Optional[ActorOverlay]]
    for actor_id in range(actor_overlay_table_length):
        (
            vrom_start,
            vrom_end,
            vram_start,
            vram_end,
            loaded_ram_addr,  # useless here
            actor_init_vram_start,
            name_vram_start,
            alloc_type,
            num_loaded,  # useless here
        ) = actor_overlay_struct.unpack_from(
            rom.file_code.data,
            rom.version_info.actor_overlay_table_code_offset
            + actor_id * actor_overlay_struct.size,
        )

        if actor_init_vram_start == 0:
            # unset entry
            actor_overlay = None
        else:
            is_overlay = not (
                vrom_start == 0 and vrom_end == 0 and vram_start == 0 and vram_end == 0
            )

            assert rom.version_info.code_vram_start <= name_vram_start

            if is_overlay:
                assert vrom_start <= vrom_end
                assert vram_start <= vram_end
                assert vram_start <= actor_init_vram_start
                assert actor_init_vram_start < vram_end

                actor_overlay_file = rom.find_file_by_vrom(vrom_start)
                assert actor_overlay_file.dma_entry.vrom_start == vrom_start
                assert actor_overlay_file.dma_entry.vrom_end == vrom_end

            name_code_offset_start = name_vram_start - rom.version_info.code_vram_start
            assert name_code_offset_start < len(rom.file_code.data)

            name_code_offset_end = name_code_offset_start

            while rom.file_code.data[name_code_offset_end] != 0:
                name_code_offset_end += 1
                assert name_code_offset_end <= len(rom.file_code.data)
                assert name_code_offset_end - name_code_offset_start < 100

            # end + 1 to count the trailing '\0'
            name_code_offset_ranges.append(
                (name_code_offset_start, name_code_offset_end + 1)
            )

            name = codecs.decode(
                rom.file_code.data[name_code_offset_start:name_code_offset_end], "ascii"
            )

            actor_overlay = ActorOverlay(
                actor_overlay_file if is_overlay else None,
                vram_start,
                vram_end,
                actor_init_vram_start,
                name,
                alloc_type,
            )

        actor_overlay_table[actor_id] = actor_overlay

        if actor_overlay is not None and actor_overlay.file is not None:
            actor_overlay.file.moveable_vrom = True

        log.trace("{:03} {}", actor_id, actor_overlay)

    pyrt.free_strings(
        rom.file_code.allocator, name_code_offset_ranges, rom.file_code.data
    )
    log.debug("rom.file_code.allocator = {}", rom.file_code.allocator)

    module_data = pyrti.modules_data[TASK]  # type: ActorOverlayTable
    module_data.actor_overlay_table = actor_overlay_table


def pack_actor_overlay_table_names(
    pyrti,  # type: pyrt.PyRTInterface
):
    module_data = pyrti.modules_data[TASK]  # type: ActorOverlayTable

    rom = pyrti.rom

    for actor_overlay in module_data.actor_overlay_table:
        if actor_overlay is None:
            continue

        name = actor_overlay.name
        if name in module_data.names_vram_start:
            continue

        (
            name_code_offset_start,
            name_code_offset_end,
        ) = rom.file_code.allocator.alloc(len(name) + 1)
        rom.file_code.data[name_code_offset_start:name_code_offset_end] = (
            name.encode("ascii") + b"\x00"
        )
        name_vram_start = rom.version_info.code_vram_start + name_code_offset_start
        module_data.names_vram_start[name] = name_vram_start


def pack_actor_overlay_table(
    pyrti,  # type: pyrt.PyRTInterface
):
    module_data = pyrti.modules_data[TASK]  # type: ActorOverlayTable

    rom = pyrti.rom
    code_data = rom.file_code.data

    assert (
        len(module_data.actor_overlay_table)
        <= rom.version_info.actor_overlay_table_length
    )

    for actor_id, actor_overlay in enumerate(module_data.actor_overlay_table):
        if actor_overlay is not None:
            if actor_overlay.file is not None:
                vrom_start = actor_overlay.file.dma_entry.vrom_start
                vrom_end = actor_overlay.file.dma_entry.vrom_end
            else:
                vrom_start = 0
                vrom_end = 0
            # TODO may want to make vram Optional if not an overlay
            vram_start = actor_overlay.vram_start
            vram_end = actor_overlay.vram_end
            actor_init_vram_start = actor_overlay.actor_init_vram_start
            name_vram_start = module_data.names_vram_start[actor_overlay.name]
            alloc_type = actor_overlay.alloc_type
        else:
            vrom_start = 0
            vrom_end = 0
            vram_start = 0
            vram_end = 0
            actor_init_vram_start = 0
            name_vram_start = 0
            alloc_type = 0
        loaded_ram_addr = 0
        num_loaded = 0
        actor_overlay_struct.pack_into(
            code_data,
            rom.version_info.actor_overlay_table_code_offset
            + actor_id * actor_overlay_struct.size,
            vrom_start,
            vrom_end,
            vram_start,
            vram_end,
            loaded_ram_addr,
            actor_init_vram_start,
            name_vram_start,
            alloc_type,
            num_loaded,
        )


def register_pyrt_module(
    pyrti,  # type: pyrt.PyRTInterface
):
    pyrti.modules_data[TASK] = ActorOverlayTable()
    pyrti.add_event_listener(pyrt.EVENT_PARSE_ROM, parse_actor_overlay_table)
    pyrti.add_event_listener(
        pyrt.EVENT_PACK_ROM_BEFORE_FILE_ALLOC, pack_actor_overlay_table_names
    )
    pyrti.add_event_listener(
        pyrt.EVENT_PACK_ROM_AFTER_FILE_ALLOC, pack_actor_overlay_table
    )


TASK = "actor overlay table"

pyrt_module_info = pyrt.ModuleInfo(
    task=TASK,
    description="Handles parsing and packing the actor overlay table.",
    register=register_pyrt_module,
)
