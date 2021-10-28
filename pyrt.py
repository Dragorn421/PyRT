#!/usr/bin/env python3

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
    from typing import List

import struct


dma_entry_struct = struct.Struct(">IIII")
assert dma_entry_struct.size == 0x10

u32_struct = struct.Struct(">I")
assert u32_struct.size == 4

rom_file_struct = struct.Struct(">II")
assert rom_file_struct.size == 8

actor_overlay_struct = struct.Struct(">IIIIIIIHbx")
assert actor_overlay_struct.size == 0x20

scene_table_entry_struct = struct.Struct(">IIIIBBBB")
assert scene_table_entry_struct.size == 0x14


class VersionInfo:
    def __init__(self, **kwargs):
        # TODO proper constructor and version info handling once stuff works
        self.__dict__.update(kwargs)


version_info_mq_debug = VersionInfo(
    dmaentry_index_dmadata=2,
    dmaentry_index_boot=1,
    dmadata_rom_start=0x012F70,
    dma_table_filenames_boot_offset=0x00A06C - 0x001060,
    boot_vram_start=0x80000460,
    dmaentry_index_code=28,
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
        file,
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
        scene_file,
        title_file,
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
        dma_entries = self.parse_dma_table(data)
        self.files = []  # type: List[RomFile]
        for dma_entry in dma_entries:
            rom_end = dma_entry.rom_start + (dma_entry.vrom_end - dma_entry.vrom_start)
            romfile = RomFile(
                data[dma_entry.rom_start : rom_end],
                dma_entry,
            )
            self.files.append(romfile)
        self.file_dmadata = self.files[self.version_info.dmaentry_index_dmadata]
        self.file_code = self.files[self.version_info.dmaentry_index_code]
        self.object_table = self.parse_object_table()
        self.actor_overlay_table = self.parse_actor_overlay_table()
        self.scene_table = self.parse_scene_table()
        # self.room_files = self.parse_scene_headers() # TODO
        self.find_unaccounted(data)

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

    def parse_object_table(self):
        (object_table_length,) = u32_struct.unpack_from(
            self.file_code.data, self.version_info.object_table_length_code_offset
        )
        object_table = [None] * object_table_length  # type: List[RomFile]
        for object_id in range(object_table_length):
            vrom_start, vrom_end = rom_file_struct.unpack_from(
                self.file_code.data,
                self.version_info.object_table_code_offset
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
                object_file = self.find_file_by_vrom(vrom_start)
                assert object_file.dma_entry.vrom_start == vrom_start
                assert object_file.dma_entry.vrom_end == vrom_end
            object_table[object_id] = object_file
            print(
                "{:03}".format(object_id),
                object_file.dma_entry if object_file is not None else "-",
            )
        return object_table

    def parse_actor_overlay_table(self):
        actor_overlay_table_length = self.version_info.actor_overlay_table_length
        actor_overlay_table = [
            None
        ] * actor_overlay_table_length  # type: List[ActorOverlay]
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
                self.file_code.data,
                self.version_info.actor_overlay_table_code_offset
                + actor_id * actor_overlay_struct.size,
            )

            if actor_init_vram_start == 0:
                # unset entry
                actor_overlay = None
            else:
                is_overlay = not (
                    vrom_start == 0
                    and vrom_end == 0
                    and vram_start == 0
                    and vram_end == 0
                )

                assert self.version_info.code_vram_start <= name_vram_start

                if is_overlay:
                    assert vrom_start <= vrom_end
                    assert vram_start <= vram_end
                    assert vram_start <= actor_init_vram_start
                    assert actor_init_vram_start < vram_end

                    actor_overlay_file = self.find_file_by_vrom(vrom_start)
                    assert actor_overlay_file.dma_entry.vrom_start == vrom_start
                    assert actor_overlay_file.dma_entry.vrom_end == vrom_end

                name_code_offset_start = (
                    name_vram_start - self.version_info.code_vram_start
                )
                assert name_code_offset_start < len(self.file_code.data)

                name_code_offset_end = name_code_offset_start

                while self.file_code.data[name_code_offset_end] != 0:
                    name_code_offset_end += 1
                    assert name_code_offset_end <= len(self.file_code.data)
                    assert name_code_offset_end - name_code_offset_start < 100

                name = self.file_code.data[
                    name_code_offset_start:name_code_offset_end
                ].decode("ascii")

                actor_overlay = ActorOverlay(
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
        return actor_overlay_table

    def parse_scene_table(self):
        scene_table_length = self.version_info.scene_table_length

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
                self.file_code.data,
                self.version_info.scene_table_code_offset
                + scene_id * scene_table_entry_struct.size,
            )
            assert scene_vrom_start <= scene_vrom_end
            assert title_vrom_start <= title_vrom_end

            scene_file = self.find_file_by_vrom(scene_vrom_start)
            assert scene_file.dma_entry.vrom_start == scene_vrom_start
            assert scene_file.dma_entry.vrom_end == scene_vrom_end

            if title_vrom_start == 0 and title_vrom_end == 0:
                # untitled scene
                title_file = None
            else:
                # titled scene
                title_file = self.find_file_by_vrom(title_vrom_start)
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
            print(
                "{:03}".format(scene_id),
                scene_table_entry if scene_table_entry is not None else "-",
            )
        return scene_table

    def find_file_by_vrom(self, vrom):
        matching_files = [
            file
            for file in self.files
            if vrom >= file.dma_entry.vrom_start and vrom < file.dma_entry.vrom_end
        ]
        assert len(matching_files) == 1
        return matching_files[0]

    def write(self, out):
        # tag moveable files rom/vrom-wise
        moveable_vrom = set()
        moveable_vrom.update(file for file in self.object_table)
        moveable_vrom.update(
            actor_overlay.file
            for actor_overlay in self.actor_overlay_table
            if actor_overlay is not None and actor_overlay.file is not None
        )
        moveable_vrom.update(
            scene_table_entry.scene_file for scene_table_entry in self.scene_table
        )

        # TODO can all other files really move?
        moveable_rom = set(self.files)
        moveable_rom.remove(self.files[0])  # TODO makerom
        moveable_rom.remove(self.files[1])  # TODO boot
        moveable_rom.remove(self.file_dmadata)
        # normalize vrom usage
        # TODO
        dynamic_vrom_ranges = (
            ...
        )  # strands where vrom isn't taken by an "immoveable vrom file"

        # max_vrom can be arbitrarily large, just need enough space
        max_vrom = 128 * (2 ** 10) ** 2  # 128 MB
        dynamic_vrom_ranges = [(0, max_vrom)]
        for file in self.files:
            if file not in moveable_vrom:
                static_vrom_start = file.dma_entry.vrom_start
                static_vrom_end = file.dma_entry.vrom_end
                for i, (dynamic_vrom_start, dynamic_vrom_end) in enumerate(dynamic_vrom_ranges):
                    ...

        # fit moveable vrom files in the space highlighted by dynamic_vrom_ranges,
        # shrinking those ranges as we go

        # normalize rom usage

        # update tables

        # write
        out.write(...)


def main():
    version_info = version_info_mq_debug
    with open("oot-mq-debug.z64", "rb") as f:
        data = f.read()
    rom = ROM(version_info, data)
    with open("oot-build.z64", "wb") as f:
        rom.write(f)


if __name__ == "__main__":
    main()
