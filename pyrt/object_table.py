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

from pathlib import Path


u32_struct = pyrt.u32_struct
rom_file_struct = pyrt.rom_file_struct


class ObjectTable:
    def __init__(self):
        self.object_table_length = None
        self.object_table = None  # type: List[Optional[pyrt.RomFile]]


def parse_object_table(
    pyrti,  # type: pyrt.PyRTInterface
):
    log = pyrti.logging_helper.get_logger(__name__)

    log.info("Parsing the object table...")

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

        log.trace(
            "{:03} {}",
            object_id,
            object_file.dma_entry if object_file is not None else "-",
        )

    module_data = pyrti.modules_data[TASK]  # type: ObjectTable
    module_data.object_table_length = object_table_length
    module_data.object_table = object_table


def dump_object_files(
    pyrti,  # type: pyrt.PyRTInterface
):
    log = pyrti.logging_helper.get_logger(__name__)

    module_data = pyrti.modules_data[TASK]  # type: ObjectTable

    dump_root = Path("objects")
    dump_root.mkdir(parents=True, exist_ok=True)

    for object_id, file in enumerate(module_data.object_table):
        if file is not None:
            file_name = file.dma_entry.name
        else:
            file_name = "unused"
        dump_file_dirname = "{:03}__{}".format(object_id, file_name)
        dump_file_dirpath = dump_root / dump_file_dirname
        dump_file_dirpath.mkdir(parents=True, exist_ok=True)

        if file is not None:
            dump_file_path = dump_file_dirpath / "object.zobj"
            with dump_file_path.open("wb") as dump_file:
                dump_file.write(file.data)


def load_object_files(
    pyrti,  # type: pyrt.PyRTInterface
):
    log = pyrti.logging_helper.get_logger(__name__)

    module_data = pyrti.modules_data[TASK]  # type: ObjectTable

    rom = pyrti.rom

    load_root = Path("objects")

    for load_file_dirpath in load_root.iterdir():
        assert load_file_dirpath.is_dir()
        m = pyrt.leading_number.match(load_file_dirpath.name)
        if m is None:
            raise Exception(
                "Can't find a leading number in directory name", load_file_dirpath.name
            )
        object_id_str = m.group(1)
        object_id = int(object_id_str, 0)
        assert object_id < len(module_data.object_table)
        rom_file = module_data.object_table[object_id]
        load_file_path = load_file_dirpath / "object.zobj"
        if load_file_path.exists():
            assert load_file_path.is_file()
            with load_file_path.open("rb") as load_file:
                data = load_file.read()

            # TODO set dma_entry.name
            if rom_file is None:
                rom_file = rom.new_file(data)
            else:
                rom_file.data = data
        else:
            if rom_file is not None:
                # TODO delete file from the rom as well
                module_data.object_table[object_id] = None


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
    pyrti.add_event_listener(pyrt.EVENT_PARSE_ROM, parse_object_table)
    pyrti.add_event_listener(pyrt.EVENT_DUMP_FILES, dump_object_files)
    pyrti.add_event_listener(pyrt.EVENT_LOAD_FILES, load_object_files)
    pyrti.add_event_listener(pyrt.EVENT_PACK_ROM_AFTER_FILE_ALLOC, pack_object_table)


TASK = "object table"

pyrt_module_info = pyrt.ModuleInfo(
    task=TASK,
    description="Handles parsing and packing the object table.",
    register=register_pyrt_module,
)
