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
    from typing import List, Dict
    from . import scene_table

import struct


u32_struct = pyrt.u32_struct
rom_file_struct = pyrt.rom_file_struct

scene_header_command_struct = struct.Struct(">BBxxI")
assert scene_header_command_struct.size == 8


class SceneHeaderRoomLists:
    def __init__(self):
        self.rooms_by_scene = (
            None
        )  # type: Dict[scene_table.SceneTableEntry, List[pyrt.RomFile]]


def find_alternate_headers(scene_data):
    header_offsets = []
    offset = 0
    code = None
    while code != 0x14:
        (code, data1, data2) = scene_header_command_struct.unpack_from(
            scene_data, offset
        )
        offset += scene_header_command_struct.size
        if code != 0x18:
            continue
        assert (data2 >> 24) == 0x02
        alternate_headers_list_offset = data2 & 0xFFFFFF
        print(
            "alternate_headers_list_offset = {:06X}".format(
                alternate_headers_list_offset
            )
        )
        while alternate_headers_list_offset + u32_struct.size <= len(scene_data):
            (alternate_header_segment_offset,) = u32_struct.unpack_from(
                scene_data,
                alternate_headers_list_offset,
            )
            alternate_headers_list_offset += u32_struct.size
            if alternate_header_segment_offset == 0:
                continue
            if (alternate_header_segment_offset >> 24) != 0x02:
                break
            alternate_header_offset = alternate_header_segment_offset & 0xFFFFFF
            # check if the data at the offset looks like headers
            alt_offset = alternate_header_offset
            alt_code = None
            while (
                alt_code != 0x14
                and alt_offset + scene_header_command_struct.size <= len(scene_data)
            ):
                (
                    alt_code,
                    alt_data1,
                    alt_data2,
                ) = scene_header_command_struct.unpack_from(scene_data, alt_offset)
                alt_offset += scene_header_command_struct.size
                # invalid command
                if alt_code >= 0x1A:
                    break
                # invalid commands in the context of alternate scene headers
                if alt_code in {0x01, 0x0A, 0x0B, 0x18}:
                    break
                # valid commands if data2 is a valid segment offset
                # (the segment is always the scene file)
                if alt_code in {0x00, 0x03, 0x04, 0x06, 0x0E, 0x0F, 0x13}:
                    if (data2 >> 24) != 0x02:
                        break
                    if (data2 & 0xFFFFFF) >= len(scene_data):
                        break
            if alt_code == 0x14:
                header_offsets.append(alternate_header_offset)
            else:
                break
    return header_offsets


def parse_scene_headers(
    pyrti,  # type: pyrt.PyRTInterface
):
    rom = pyrti.rom

    module_data_scene_table = pyrti.modules_data[
        TASK_SCENE_TABLE
    ]  # type: scene_table.SceneTable

    rooms_by_scene = (
        dict()
    )  # type: Dict[scene_table.SceneTableEntry, List[pyrt.RomFile]]
    for scene_table_entry in module_data_scene_table.scene_table:
        scene_data = scene_table_entry.scene_file.data
        header_offsets = [0] + find_alternate_headers(scene_data)
        # find room list from all headers
        for offset in header_offsets:
            code = None
            room_list = []  # type: List[pyrt.RomFile]
            while code != 0x14:
                (code, data1, data2) = scene_header_command_struct.unpack_from(
                    scene_data, offset
                )
                offset += scene_header_command_struct.size
                if code != 0x04:
                    continue
                room_list_length = data1
                room_list_segment_offset = data2
                assert (room_list_segment_offset >> 24) == 0x02
                room_list_offset = room_list_segment_offset & 0xFFFFFF
                assert (
                    room_list_offset + room_list_length * rom_file_struct.size
                    <= len(scene_data)
                )
                for room_index in range(room_list_length):
                    (room_vrom_start, room_vrom_end) = rom_file_struct.unpack_from(
                        scene_data,
                        room_list_offset + room_index * rom_file_struct.size,
                    )
                    assert room_vrom_start <= room_vrom_end
                    room_file = rom.find_file_by_vrom(room_vrom_start)
                    assert room_vrom_start == room_file.dma_entry.vrom_start
                    assert room_vrom_end == room_file.dma_entry.vrom_end
                    room_list.append(room_file)

                    room_file.moveable_vrom = True
            if scene_table_entry not in rooms_by_scene:
                rooms_by_scene[scene_table_entry] = room_list
                print(scene_table_entry)
                print(
                    "\n".join(
                        " #{:<2} {}".format(room_index, room.dma_entry)
                        for room_index, room in enumerate(room_list)
                    )
                )
            else:
                # TODO support different room lists for each header
                # for now, just check that all room lists are the same
                assert rooms_by_scene[scene_table_entry] == room_list

    module_data = pyrti.modules_data[TASK]  # type: SceneHeaderRoomLists
    module_data.rooms_by_scene = rooms_by_scene


def pack_room_lists(
    pyrti,  # type: pyrt.PyRTInterface
):
    module_data = pyrti.modules_data[TASK]  # type: SceneHeaderRoomLists

    for scene_table_entry, room_list in module_data.rooms_by_scene.items():
        print("Scene ", scene_table_entry.scene_file.dma_entry)
        scene_data = bytearray(scene_table_entry.scene_file.data)
        header_offsets = [0] + find_alternate_headers(scene_data)
        # find room list from all headers
        for offset in header_offsets:
            print("  Header 0x{:06X}".format(offset))
            code = None
            while code != 0x14:
                (code, data1, data2) = scene_header_command_struct.unpack_from(
                    scene_data, offset
                )
                offset += scene_header_command_struct.size
                if code != 0x04:
                    continue
                room_list_length = data1
                assert room_list_length == len(room_list)
                room_list_segment_offset = data2
                assert (room_list_segment_offset >> 24) == 0x02
                room_list_offset = room_list_segment_offset & 0xFFFFFF
                assert (
                    room_list_offset + room_list_length * rom_file_struct.size
                    <= len(scene_data)
                )
                for room_index, room_file in enumerate(room_list):
                    rom_file_struct.pack_into(
                        scene_data,
                        room_list_offset + room_index * rom_file_struct.size,
                        room_file.dma_entry.vrom_start,
                        room_file.dma_entry.vrom_end,
                    )
                    print("    Room {}".format(room_index), room_file.dma_entry)
        scene_table_entry.scene_file.data = scene_data


def register_pyrt_module(
    pyrti,  # type: pyrt.PyRTInterface
):
    pyrti.modules_data[TASK] = SceneHeaderRoomLists()
    pyrti.add_event_listener(pyrt.EVENT_DMA_LOAD_DONE, parse_scene_headers)
    pyrti.add_event_listener(pyrt.EVENT_ROM_VROM_REALLOC_DONE, pack_room_lists)


TASK = "scene header room lists"
TASK_SCENE_TABLE = "scene table"

pyrt_module_info = pyrt.ModuleInfo(
    task=TASK,
    task_dependencies={TASK_SCENE_TABLE},
    description="Handles parsing and packing the room lists in scene headers.",
    register=register_pyrt_module,
)
