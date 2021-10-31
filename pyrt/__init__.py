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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import List, Dict, Set, Tuple, Optional, Callable
    from types import ModuleType

import os

import struct
import bisect


class Ranges:
    def __init__(
        self,
        ranges=[],  # type: List[Tuple[int,int]]
    ):
        """
        ranges is a list of (start, end) tuples, sorted like
        ranges[i] start < ranges[i] end < ranges[i+1] start
        (the class methods maintain that order)
        """
        self.ranges = ranges

    def add_range(self, add_start, add_end):
        ranges = self.ranges

        # ranges[i-1] end < add_start <= ranges[i] end
        i = bisect.bisect_left([end for start, end in ranges], add_start)

        while i < len(ranges):
            start, end = ranges[i]
            if add_end < start:
                break
            if add_start > start:
                add_start = start
            if add_end < end:
                add_end = end
            self.ranges.pop(i)
        self.ranges.insert(i, (add_start, add_end))

    def exclude_range(self, exclude_start, exclude_end):
        ranges = self.ranges

        # ranges[i-1] end <= exclude_start < ranges[i] end
        i = bisect.bisect_right([end for start, end in ranges], exclude_start)

        while i < len(ranges):
            start, end = ranges[i]
            # stop if range starts after exclude range ends
            if exclude_end <= start:
                break

            # start < exclude_end
            if exclude_start <= start and exclude_end >= end:
                # exclude_start <= start <= end <= exclude_end
                ranges.pop(i)  # range completely excluded
            elif exclude_start >= start and exclude_end <= end:
                # start <= exclude_start <= exclude_end <= end
                ranges.pop(i)
                if start != exclude_start:
                    ranges.insert(i, (start, exclude_start))
                    i += 1
                if exclude_end != end:
                    ranges.insert(i, (exclude_end, end))
                    i += 1
            elif exclude_start >= start and exclude_start < end:
                # start <= exclude_start < end (< exclude_end)
                ranges.pop(i)
                if start != exclude_start:
                    ranges.insert(i, (start, exclude_start))
                    i += 1
            elif exclude_end > start and exclude_end <= end:
                # (exclude_start <) start < exclude_end <= end
                ranges.pop(i)
                if exclude_end != end:
                    ranges.insert(i, (exclude_end, end))
                    i += 1
            else:
                # disjointed intervals
                raise AssertionError(
                    "disjointed: {:X}-{:X} {:X}-{:X}".format(
                        start, end, exclude_start, exclude_end
                    )
                )

    def __repr__(self):
        return "Ranges({!r})".format(self.ranges)

    def __str__(self):
        return "Ranges " + ",".join(
            "{:X}-{:X}".format(start, end) for start, end in self.ranges
        )


class RangesAscendingLength:
    def __init__(
        self,
        ranges,  # type: List[Tuple[int,int]]
    ):
        self.ranges = ranges
        self.ranges.sort(key=lambda range_limits: range_limits[1] - range_limits[0])

    def find_and_exclude_range(self, length):
        """
        length = end - start
        maintains (ranges[i] length) < (ranges[i+1] length)
        """
        ranges = self.ranges

        # ranges[i-1] length < length <= ranges[i] length
        i = bisect.bisect_left([end - start for start, end in ranges], length)

        start, end = ranges.pop(i)
        exclude_start = start
        exclude_end = start + length

        remain_start = exclude_end
        remain_end = end
        remain_length = remain_end - remain_start
        if remain_length != 0:
            # ranges[i-1] length < remain_length <= ranges[i] length
            i = bisect.bisect_left(
                [end - start for start, end in ranges], remain_length
            )
            ranges.insert(i, (remain_start, remain_end))

        return exclude_start, exclude_end

    def __repr__(self):
        return "RangesAscendingLength({!r})".format(self.ranges)

    def __str__(self):
        return "RangesAscendingLength " + ",".join(
            "{:X}-{:X}".format(start, end) for start, end in self.ranges
        )


dma_entry_struct = struct.Struct(">IIII")
assert dma_entry_struct.size == 0x10

u32_struct = struct.Struct(">I")
assert u32_struct.size == 4

rom_file_struct = struct.Struct(">II")
assert rom_file_struct.size == 8

scene_header_command_struct = struct.Struct(">BBxxI")
assert scene_header_command_struct.size == 8


class VersionInfo:
    def __init__(self, **kwargs):
        # TODO proper constructor and version info handling once stuff works
        self.__dict__.update(kwargs)


version_info_mq_debug = VersionInfo(
    dmaentry_index_makerom=0,
    dmaentry_index_boot=1,
    dmaentry_index_dmadata=2,
    dmaentry_index_code=28,
    dmadata_rom_start=0x012F70,
    dma_table_filenames_boot_offset=0x00A06C - 0x001060,
    boot_vram_start=0x80000460,
    code_vram_start=0x8001CE60,
    # gObjectTable
    object_table_length_code_offset=0x80127524 - 0x8001CE60,
    object_table_code_offset=0x80127528 - 0x8001CE60,
    # gActorOverlayTable
    actor_overlay_table_length=471,
    actor_overlay_table_code_offset=0x801162A0 - 0x8001CE60,
    # gSceneTable
    scene_table_length=110,
    scene_table_code_offset=0x80129A10 - 0x8001CE60,
    # gEffectSsOverlayTable TODO
    # gGameStateOverlayTable TODO
    # gEntranceTable TODO
)


class DmaEntry:
    def __init__(self, vrom_start, vrom_end, rom_start, rom_end, name=None):
        self.vrom_start = vrom_start
        self.vrom_end = vrom_end
        self.rom_start = rom_start
        self.rom_end = rom_end
        self.name = name

    def __str__(self):
        return " ".join(
            (
                "VROM 0x{0.vrom_start:08X}-0x{0.vrom_end:08X}",
                (
                    "ROM 0x{0.rom_start:08X}-0x{0.rom_end:08X}"
                    if self.rom_end != 0
                    else "ROM 0x{0.rom_start:08X}"
                ),
                self.name if self.name is not None else "-",
            )
        ).format(self)

    def __repr__(self):
        return (
            "DmaEntry(0x{0.vrom_start:X}, 0x{0.vrom_end:X},"
            " 0x{0.rom_start:X}, 0x{0.rom_end:X}, {0.name!r})"
        ).format(self)


class RomFile:
    def __init__(
        self,
        data,  # type: bytes
        dma_entry,  # type: DmaEntry
    ):
        self.data = data
        self.dma_entry = dma_entry


class ActorOverlay:
    def __init__(
        self,
        file,  # type: Optional[RomFile]
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


class SceneTableEntry:
    def __init__(
        self,
        scene_file,  # type: RomFile
        title_file,  # type: Optional[RomFile]
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


class ROM:
    def __init__(
        self,
        version_info,  # type: VersionInfo
        data,  # type: bytes
    ):
        self.version_info = version_info
        self.data = data

    def find_unaccounted(self, data):
        rom_size = len(data)
        is_unaccounted = [True] * rom_size

        for file in self.files:
            dma_entry = file.dma_entry
            size = dma_entry.vrom_end - dma_entry.vrom_start
            rom_start = dma_entry.rom_start
            rom_end = rom_start + size
            i = rom_start
            while i < rom_end:
                is_unaccounted[i] = False
                i += 1

        unaccounted_strand_start = 0
        prev_is_unaccounted = False
        i = 0
        while i < rom_size:
            if is_unaccounted[i]:
                if not prev_is_unaccounted:
                    unaccounted_strand_start = i
            else:
                if prev_is_unaccounted:
                    print(
                        "0x{:08X}-0x{:08X}".format(unaccounted_strand_start, i),
                        set(data[unaccounted_strand_start:i]),
                    )
            prev_is_unaccounted = is_unaccounted[i]
            i += 1

        if prev_is_unaccounted:
            print(
                "0x{:08X}-0x{:08X} (end)".format(unaccounted_strand_start, rom_size),
                set(data[unaccounted_strand_start:rom_size]),
            )

    def parse_dma_table(self, data):

        # read dmadata entry early, to get dma table length

        (
            dmadata_vrom_start,
            dmadata_vrom_end,
            dmadata_rom_start,
            dmadata_rom_end,
        ) = dma_entry_struct.unpack_from(
            data,
            self.version_info.dmadata_rom_start
            + self.version_info.dmaentry_index_dmadata * dma_entry_struct.size,
        )

        assert dmadata_rom_start == self.version_info.dmadata_rom_start
        assert dmadata_vrom_start <= dmadata_vrom_end
        assert dmadata_rom_end == 0

        dmadata_rom_end = dmadata_rom_start + (dmadata_vrom_end - dmadata_vrom_start)
        assert dmadata_rom_end <= len(data)

        # read boot entry early, to locate filenames

        (
            boot_vrom_start,
            boot_vrom_end,
            boot_rom_start,
            boot_rom_end,
        ) = dma_entry_struct.unpack_from(
            data,
            dmadata_rom_start
            + self.version_info.dmaentry_index_boot * dma_entry_struct.size,
        )

        assert boot_vrom_start <= boot_vrom_end
        assert boot_rom_end == 0

        boot_rom_end = boot_rom_start + (boot_vrom_end - boot_vrom_start)
        assert boot_rom_end <= len(data)

        def get_filename(i):
            (filename_vram_start,) = u32_struct.unpack_from(
                data,
                boot_rom_start
                + self.version_info.dma_table_filenames_boot_offset
                + i * u32_struct.size,
            )
            filename_rom_start = (
                filename_vram_start - self.version_info.boot_vram_start + boot_rom_start
            )
            assert filename_rom_start < boot_rom_end
            filename_rom_end = filename_rom_start
            while data[filename_rom_end] != 0:
                filename_rom_end += 1
                assert filename_rom_end <= boot_rom_end
                assert filename_rom_end - filename_rom_start < 100
            return data[filename_rom_start:filename_rom_end].decode("ascii")

        dma_entries = []  # type: List[DmaEntry]
        dmaentry_rom_start = dmadata_rom_start
        dmaentry_index = 0
        while dmaentry_rom_start < dmadata_rom_end:
            vrom_start, vrom_end, rom_start, rom_end = dma_entry_struct.unpack_from(
                data, dmaentry_rom_start
            )

            if not (
                vrom_start == 0 and vrom_end == 0 and rom_start == 0 and rom_end == 0
            ):
                assert vrom_start <= vrom_end
                assert rom_end == 0
                assert rom_start + (vrom_end - vrom_start) <= len(data)

                dmaentry = DmaEntry(
                    vrom_start,
                    vrom_end,
                    rom_start,
                    rom_end,
                    get_filename(dmaentry_index),
                )
                dma_entries.append(dmaentry)
                print("{:04}".format(dmaentry_index), dmaentry)

            dmaentry_rom_start += dma_entry_struct.size
            dmaentry_index += 1

        return dma_entries

    def parse_scene_headers(self):
        rooms_by_scene = dict()  # type: Dict[SceneTableEntry, List[RomFile]]
        for scene_table_entry in self.scene_table:
            scene_data = scene_table_entry.scene_file.data
            header_offsets = [0]
            # find alternate headers
            offset = 0
            code = None
            while code != 0x14:
                (code, data1, data2) = scene_header_command_struct.unpack_from(
                    scene_data, offset
                )
                offset += scene_header_command_struct.size
                if code != 0x18:
                    continue
                alternate_headers_list_offset = data2
                while alternate_headers_list_offset + u32_struct.size <= len(
                    scene_data
                ):
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
                        and alt_offset + scene_header_command_struct.size
                        <= len(scene_data)
                    ):
                        (
                            alt_code,
                            alt_data1,
                            alt_data2,
                        ) = scene_header_command_struct.unpack_from(
                            scene_data, alt_offset
                        )
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
            # find room list from all headers
            for offset in header_offsets:
                code = None
                room_list = []  # type: List[RomFile]
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
                        room_file = self.find_file_by_vrom(room_vrom_start)
                        assert room_vrom_start == room_file.dma_entry.vrom_start
                        assert room_vrom_end == room_file.dma_entry.vrom_end
                        room_list.append(room_file)
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
        return rooms_by_scene

    def find_file_by_vrom(self, vrom):
        matching_files = [
            file
            for file in self.files
            if vrom >= file.dma_entry.vrom_start and vrom < file.dma_entry.vrom_end
        ]
        assert len(matching_files) == 1
        return matching_files[0]

    def realloc_moveable_vrom(self, move_vrom):
        # tag moveable files rom/vrom-wise
        moveable_vrom = set()  # type: Set[RomFile]
        if move_vrom:
            moveable_vrom.update(file for file in self.object_table if file is not None)
            moveable_vrom.update(
                actor_overlay.file
                for actor_overlay in self.actor_overlay_table
                if actor_overlay is not None and actor_overlay.file is not None
            )
            moveable_vrom.update(
                scene_table_entry.scene_file for scene_table_entry in self.scene_table
            )
            for room_list in self.rooms_by_scene.values():
                moveable_vrom.update(room_list)

        # OoT's `DmaMgr_SendRequestImpl` limits the vrom to 64MB
        # https://github.com/zeldaret/oot/blob/f1d27bf6531fd6579d09dcf3078ee97c57b6fff1/src/boot/z_std_dma.c#L1864
        max_vrom = 0x4000000  # 64MB

        self.realloc_vrom(max_vrom, moveable_vrom)

    def realloc_vrom(self, max_vrom, moveable_vrom):
        # strands where vrom isn't taken by an "immoveable vrom file"
        dynamic_vrom_ranges = Ranges()
        dynamic_vrom_ranges.add_range(0, max_vrom)

        for file in self.files:
            if file not in moveable_vrom:
                vrom_start = file.dma_entry.vrom_start
                vrom_end = file.dma_entry.vrom_end
                dynamic_vrom_ranges.exclude_range(vrom_start, vrom_end)
                # the vrom offsets of this file won't be updated,
                # check now if the file fits the reserved vrom
                assert len(file.data) == (vrom_end - vrom_start)

        print("dynamic_vrom_ranges =", dynamic_vrom_ranges)

        # FIXME handle alignment somewhere

        # sort ranges from smallest to largest
        free_vrom_ranges = RangesAscendingLength(dynamic_vrom_ranges.ranges)
        del dynamic_vrom_ranges

        print("free_vrom_ranges =", free_vrom_ranges)

        # sort files from largest to smallest
        # If same size, sort by name. This makes the ordering consistent across
        # different executions, but TODO it would be nice to find something
        # else (like, index in the dma table), it may be faster, and would also
        # be more portable (only debug versions have the file name, I think?).
        moveable_vrom_sorted = list(moveable_vrom)
        moveable_vrom_sorted.sort(
            key=lambda file: (len(file.data), file.dma_entry.name),
            reverse=True,
        )

        # fit moveable vrom files in the space highlighted by dynamic_vrom_ranges,
        # shrinking those ranges as we go
        for file in moveable_vrom_sorted:
            start, end = free_vrom_ranges.find_and_exclude_range(len(file.data))
            file.dma_entry.vrom_start = start
            file.dma_entry.vrom_end = end
            print("VROM> {}".format(file.dma_entry))

    def realloc_moveable_rom(self, move_rom):
        # TODO can all other files really move?
        if move_rom:
            moveable_rom = set(self.files)
            moveable_rom.remove(self.file_makerom)
            moveable_rom.remove(self.file_boot)
            moveable_rom.remove(self.file_dmadata)
            # TODO these audio files can move if the rom pointers in code are updated accordingly
            # https://github.com/zeldaret/oot/blob/bf0f26db9b9c2325cea249d6c8e0ec3b5152bcd6/src/code/audio_load.c#L1109
            moveable_rom.remove(self.files[3])  # Audiobank
            moveable_rom.remove(self.files[4])  # Audioseq
            moveable_rom.remove(self.files[5])  # Audiotable
        else:
            moveable_rom = set()

        # TODO is max_rom limited by anything apart from max_vrom to prevent eg a 128MB rom?
        max_rom = 0x4000000  # 64MB

        self.realloc_rom(max_rom, moveable_rom)

    def realloc_rom(self, max_rom, moveable_rom):
        # strands where rom isn't taken by an "immoveable rom file"
        dynamic_rom_ranges = Ranges()
        dynamic_rom_ranges.add_range(0, max_rom)

        for file in self.files:
            if file not in moveable_rom:
                dynamic_rom_ranges.exclude_range(
                    file.dma_entry.rom_start,
                    file.dma_entry.rom_start + len(file.data),
                )

        print("dynamic_rom_ranges =", dynamic_rom_ranges)

        # sort ranges from smallest to largest
        free_rom_ranges = RangesAscendingLength(dynamic_rom_ranges.ranges)
        del dynamic_rom_ranges

        print("free_rom_ranges =", free_rom_ranges)

        # sort files from largest to smallest
        moveable_rom_sorted = list(moveable_rom)
        # TODO see the vrom equivalent moveable_vrom_sorted
        moveable_rom_sorted.sort(
            key=lambda file: (len(file.data), file.dma_entry.name),
            reverse=True,
        )

        # fit moveable rom files in the space highlighted by dynamic_rom_ranges,
        # shrinking those ranges as we go
        for file in moveable_rom_sorted:
            start, end = free_rom_ranges.find_and_exclude_range(len(file.data))
            file.dma_entry.rom_start = start
            file.dma_entry.rom_end = 0  # TODO ?
            print("ROM> {}".format(file.dma_entry))

    def pack_dma_table(self):
        assert self.file_makerom == self.files[self.version_info.dmaentry_index_makerom]
        assert self.file_boot == self.files[self.version_info.dmaentry_index_boot]
        assert self.file_dmadata == self.files[self.version_info.dmaentry_index_dmadata]
        assert self.file_code == self.files[self.version_info.dmaentry_index_code]

        dmadata_data = bytearray(len(self.file_dmadata.data))
        print("Built DMA table:")
        for i, file in enumerate(self.files):
            dma_entry = file.dma_entry
            print(dma_entry)
            dma_entry_struct.pack_into(
                dmadata_data,
                i * dma_entry_struct.size,
                dma_entry.vrom_start,
                dma_entry.vrom_end,
                dma_entry.rom_start,
                dma_entry.rom_end,
            )
            # FIXME use dma_entry.name
        self.file_dmadata.data = dmadata_data

    def pack_room_lists(self):
        # TODO mostly copypasted from parse_scene_headers, make code common
        for scene_table_entry, room_list in self.rooms_by_scene.items():
            print("Scene ", scene_table_entry.scene_file.dma_entry)
            scene_data = bytearray(scene_table_entry.scene_file.data)
            header_offsets = [0]
            # find alternate headers
            offset = 0
            code = None
            while code != 0x14:
                (code, data1, data2) = scene_header_command_struct.unpack_from(
                    scene_data, offset
                )
                offset += scene_header_command_struct.size
                if code != 0x18:
                    continue
                # FIXME there are fixes like this line not present in the og code that got copypasted
                # TODO check segment 2
                alternate_headers_list_offset = data2 & 0xFFFFFF
                import sys

                print(
                    "alternate_headers_list_offset = {:06X}".format(
                        alternate_headers_list_offset
                    ),
                    file=sys.stderr,
                )
                while alternate_headers_list_offset + u32_struct.size <= len(
                    scene_data
                ):
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
                        and alt_offset + scene_header_command_struct.size
                        <= len(scene_data)
                    ):
                        (
                            alt_code,
                            alt_data1,
                            alt_data2,
                        ) = scene_header_command_struct.unpack_from(
                            scene_data, alt_offset
                        )
                        alt_offset += (
                            scene_header_command_struct.size
                        )  # FIXME another uncopied bugfix
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

    def write(self, out):
        rom_data = bytearray(
            max(file.dma_entry.rom_start + len(file.data) for file in self.files)
        )
        print(len(rom_data))
        for file in self.files:
            rom_data[
                file.dma_entry.rom_start : file.dma_entry.rom_start + len(file.data)
            ] = file.data
        out.write(rom_data)


class ModuleInfo:
    def __init__(
        self,
        task,  # type: str
        register,  # type: Callable[[PyRTInterface],None]
        task_dependencies={},  # type: Set[str]
        description="",  # type: str
    ):
        self.task = task
        self.register = register
        self.task_dependencies = task_dependencies
        self.description = description

    def __repr__(self) -> str:
        return (
            "ModuleInfo("
            + ", ".join(
                repr(v)
                for v in (
                    self.task,
                    self.register,
                    self.task_dependencies,
                    self.description,
                )
            )
            + ")"
        )

    def __str__(self) -> str:
        return (
            self.task
            + ((" - " + self.description) if self.description else "")
            + (
                ("(depends on " + ", ".join(self.task_dependencies) + ")")
                if self.task_dependencies
                else ""
            )
        )


class PyRTEvent:
    def __init__(
        self,
        id,  # type: str
        description,  # type: str
    ):
        self.id = id
        self.description = description

    def __repr__(self) -> str:
        return (
            "PyRTEvent("
            + ", ".join(
                repr(v)
                for v in (
                    self.id,
                    self.description,
                )
            )
            + ")"
        )

    def __str__(self) -> str:
        return self.id + " - " + self.description


EVENT_DMA_LOAD_DONE = PyRTEvent(
    "DMA load done",
    "After the DMA table has been parsed and the ROM split into the corresponding files.",
)

EVENT_ROM_VROM_REALLOC_DONE = PyRTEvent(
    "ROM/VROM realloc done",
    "After the file offsets in VROM/ROM got updated.",
)


class PyRTInterface:
    def __init__(
        self,
        rom,  # type: ROM
    ):
        self.rom = rom
        self.modules = []  # type: List[ModuleType]
        self.event_listeners = (
            dict()
        )  # type: Dict[PyRTEvent, List[Callable[[PyRTInterface],None]]]

    def load_modules(self):
        import importlib

        modules_dir_path = os.path.dirname(__file__)
        print("Looking for modules in", modules_dir_path)
        print("__package__ =", __package__)

        module_names_by_task = dict()

        with os.scandir(modules_dir_path) as dir_iter:
            for dir_entry in dir_iter:
                # skip __pycache__ and __init__.py more explicitly
                if dir_entry.name.startswith("_"):
                    print("Skipping", dir_entry.path, "(_ prefix)")
                    continue
                if not dir_entry.is_file():
                    print("Skipping", dir_entry.path, "(not a file)")
                    continue
                if not dir_entry.name.endswith(".py"):
                    print("Skipping", dir_entry.path, "(not a .py file)")
                    continue
                module_name = dir_entry.name[: -len(".py")]
                print("Loading", module_name)
                module = importlib.import_module("." + module_name, __package__)
                if not hasattr(module, "pyrt_module_info"):
                    print("Skipping module", module_name, "(no pyrt_module_info)")
                    continue
                module_info = module.pyrt_module_info  # type: ModuleInfo
                if module_info.task in module_names_by_task:
                    raise Exception(
                        "Duplicate module task "
                        + module_info.task
                        + " (used by both "
                        + module_names_by_task[module_info.task]
                        + " and "
                        + module_name
                        + ")"
                    )
                module_names_by_task[module_info.task] = module_name
                self.modules.append(module)

    def register_modules(self):
        unregistered_modules = {
            module.pyrt_module_info.task: module for module in self.modules
        }
        while unregistered_modules:
            # find a module with no unregistered dependency
            registerable_module_item = next(
                (
                    (module_task, module)
                    for module_task, module in unregistered_modules.items()
                    if not (
                        module.pyrt_module_info.task_dependencies
                        & unregistered_modules.keys()
                    )
                ),
                None,
            )
            if registerable_module_item is None:
                print("Can't solve dependencies for remaining modules.")
                print("Skipping registration of:")
                print(unregistered_modules)
                break
            module_task, module = registerable_module_item
            module_info = module.pyrt_module_info  # type: ModuleInfo
            module_info.register(self)
            del unregistered_modules[module_task]

    def register_event(
        self,
        event,  # type: PyRTEvent
    ):
        if event in self.event_listeners:
            raise ValueError("Event already registered: " + repr(event))
        self.event_listeners[event] = []

    def raise_event(
        self,
        event,  # type: PyRTEvent
    ):
        for callback in self.event_listeners[event]:
            try:
                callback(self)
            except Exception:
                print("An error ocurred raising event =", repr(event))
                raise

    def add_event_listener(
        self,
        event,  # type: PyRTEvent
        callback,  # type: Callable[[PyRTInterface],None]
    ):
        event_listeners = self.event_listeners.get(event)
        if event_listeners is None:
            import sys

            print(repr(self.event_listeners), file=sys.stderr)
            print(id(event), file=sys.stderr)
            print([id(ev) for ev in self.event_listeners], file=sys.stderr)
            raise ValueError("Event not registered: " + repr(event))
        event_listeners.append(callback)


def main():
    version_info = version_info_mq_debug
    with open("oot-mq-debug.z64", "rb") as f:
        data = f.read()
    rom = ROM(version_info, data)

    pyrti = PyRTInterface(rom)

    pyrti.register_event(EVENT_DMA_LOAD_DONE)
    pyrti.register_event(EVENT_ROM_VROM_REALLOC_DONE)

    pyrti.load_modules()
    pyrti.register_modules()

    dma_entries = rom.parse_dma_table(rom.data)
    rom.files = []
    for dma_entry in dma_entries:
        rom_end = dma_entry.rom_start + (dma_entry.vrom_end - dma_entry.vrom_start)
        romfile = RomFile(
            rom.data[dma_entry.rom_start : rom_end],
            dma_entry,
        )
        rom.files.append(romfile)
    rom.file_makerom = rom.files[rom.version_info.dmaentry_index_makerom]
    rom.file_boot = rom.files[rom.version_info.dmaentry_index_boot]
    rom.file_dmadata = rom.files[rom.version_info.dmaentry_index_dmadata]
    rom.file_code = rom.files[rom.version_info.dmaentry_index_code]
    pyrti.raise_event(EVENT_DMA_LOAD_DONE)
    rom.rooms_by_scene = rom.parse_scene_headers()
    rom.find_unaccounted(rom.data)

    move_vrom = True
    move_rom = True

    rom.realloc_moveable_vrom(move_vrom)
    rom.realloc_moveable_rom(move_rom)

    # update tables

    rom.pack_dma_table()

    rom.code_data = bytearray(rom.file_code.data)

    pyrti.raise_event(EVENT_ROM_VROM_REALLOC_DONE)

    rom.file_code.data = rom.code_data

    # update scene headers
    rom.pack_room_lists()

    with open("oot-build.z64", "wb") as f:
        rom.write(f)
