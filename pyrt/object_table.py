import pyrt


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import List, Dict, Set, Tuple, Optional

u32_struct = pyrt.u32_struct
rom_file_struct = pyrt.rom_file_struct


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
        print(
            "{:03}".format(object_id),
            object_file.dma_entry if object_file is not None else "-",
        )
    rom.object_table = object_table


def pack_object_table(
    pyrti,  # type: pyrt.PyRTInterface
):
    rom = pyrti.rom
    code_data = rom.code_data

    # FIXME check if not going past original table length
    u32_struct.pack_into(
        code_data,
        rom.version_info.object_table_length_code_offset,
        len(rom.object_table),
    )
    for object_id, file in enumerate(rom.object_table):
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
    pyrti.add_event_listener(pyrt.EVENT_DMA_LOAD_DONE, parse_object_table)
    pyrti.add_event_listener(pyrt.EVENT_ROM_VROM_REALLOC_DONE, pack_object_table)


pyrt_module_info = pyrt.ModuleInfo(
    task="object table",
    description="Handles parsing and packing the object table.",
    register=register_pyrt_module,
)
