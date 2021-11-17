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


u32_struct = pyrt.u32_struct
rom_file_struct = pyrt.rom_file_struct


class ObjectTable:
    def __init__(self):
        self.object_table_length = None
        self.object_table = None  # type: List[Optional[pyrt.RomFile]]


def parse_object_table(
    pyrti,  # type: pyrt.PyRTInterface
):
    rom = pyrti.rom
    (object_table_length,) = u32_struct.unpack_from(
        rom.file_code.data, rom.version_info.object_table_length_code_offset
    )
    object_table = [None] * object_table_length  # type: List[Optional[pyrt.RomFile]]
    for object_id in range(object_table_length):
        vrom_start, vrom_end = rom_file_struct.unpack_from(
            rom.file_code.data,
            rom.version_info.object_table_code_offset
            + object_id * rom_file_struct.size,
        )
        assert vrom_start <= vrom_end
        if vrom_start == 0 and vrom_end == 0:
            # unset entry
            object_file = None
        elif vrom_start == vrom_end:
            # "NULL" entry
            # such entries are unused, can safely use them as if unset
            object_file = None
        else:
            object_file = rom.find_file_by_vrom(vrom_start)
            assert object_file.dma_entry.vrom_start == vrom_start
            assert object_file.dma_entry.vrom_end == vrom_end
        object_table[object_id] = object_file

        if object_file is not None:
            object_file.moveable_vrom = True

        print(
            "{:03}".format(object_id),
            object_file.dma_entry if object_file is not None else "-",
        )

    module_data = pyrti.modules_data[TASK]  # type: ObjectTable
    module_data.object_table_length = object_table_length
    module_data.object_table = object_table


def pack_object_table(
    pyrti,  # type: pyrt.PyRTInterface
):
    module_data = pyrti.modules_data[TASK]  # type: ObjectTable

    rom = pyrti.rom
    code_data = rom.file_code.data

    # TODO allow smaller object table. This uses == instead of <= to avoid
    # permanent shortening (the length is read and written from the code file)
    assert len(module_data.object_table) == module_data.object_table_length

    u32_struct.pack_into(
        code_data,
        rom.version_info.object_table_length_code_offset,
        len(module_data.object_table),
    )
    for object_id, file in enumerate(module_data.object_table):
        if file is not None:
            vrom_start = file.dma_entry.vrom_start
            vrom_end = file.dma_entry.vrom_end
        else:
            vrom_start = 0
            vrom_end = 0
        rom_file_struct.pack_into(
            code_data,
            rom.version_info.object_table_code_offset
            + object_id * rom_file_struct.size,
            vrom_start,
            vrom_end,
        )


def register_pyrt_module(
    pyrti,  # type: pyrt.PyRTInterface
):
    pyrti.modules_data[TASK] = ObjectTable()
    pyrti.add_event_listener(pyrt.EVENT_DMA_LOAD_DONE, parse_object_table)
    pyrti.add_event_listener(pyrt.EVENT_ROM_VROM_REALLOC_DONE, pack_object_table)


TASK = "object table"

pyrt_module_info = pyrt.ModuleInfo(
    task=TASK,
    description="Handles parsing and packing the object table.",
    register=register_pyrt_module,
)
