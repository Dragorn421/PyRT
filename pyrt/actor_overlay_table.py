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


actor_overlay_struct = struct.Struct(">IIIIIIIHbx")
assert actor_overlay_struct.size == 0x20


def parse_actor_overlay_table(
    pyrti,  # type: pyrt.PyRTInterface
):
    rom = pyrti.rom

    actor_overlay_table_length = rom.version_info.actor_overlay_table_length
    actor_overlay_table = [
        None
    ] * actor_overlay_table_length  # type: List[Optional[pyrt.ActorOverlay]]
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

            name = rom.file_code.data[
                name_code_offset_start:name_code_offset_end
            ].decode("ascii")

            actor_overlay = pyrt.ActorOverlay(
                actor_overlay_file if is_overlay else None,
                vram_start,
                vram_end,
                actor_init_vram_start,
                name,
                alloc_type,
            )

        actor_overlay_table[actor_id] = actor_overlay
        print(
            "{:03}".format(actor_id),
            actor_overlay if actor_overlay is not None else "-",
        )
    rom.actor_overlay_table = actor_overlay_table


def pack_actor_overlay_table(
    pyrti,  # type: pyrt.PyRTInterface
):
    rom = pyrti.rom
    code_data = rom.code_data

    # FIXME check max length

    for actor_id, actor_overlay in enumerate(rom.actor_overlay_table):
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
            # FIXME name_vram_start with actor_overlay.name
            name_vram_start = rom.version_info.code_vram_start + code_data.index(
                b"\x00"
            )
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
    pyrti.add_event_listener(pyrt.EVENT_DMA_LOAD_DONE, parse_actor_overlay_table)
    pyrti.add_event_listener(pyrt.EVENT_ROM_VROM_REALLOC_DONE, pack_actor_overlay_table)


pyrt_module_info = pyrt.ModuleInfo(
    task="actor overlay table",
    description="Handles parsing and packing the actor overlay table.",
    register=register_pyrt_module,
)
