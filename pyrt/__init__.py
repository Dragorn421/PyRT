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
    from typing import List, Dict, Set, Tuple, Optional, Callable, Any
    from types import ModuleType
    import io

import os
import logging

import struct
import math
import re


class LoggingHelper:
    trace_level = 5

    def __init__(self, root_logger_name):
        logging.addLevelName(LoggingHelper.trace_level, "TRACE")

        self.root_logger = logging.getLogger("%s.%s" % (__package__, root_logger_name))
        self.root_logger_stream_handler = logging.StreamHandler()
        self.root_logger_file_handler = None  # type: Optional[logging.FileHandler]
        self.root_logger_formatter = logging.Formatter(
            fmt="{asctime} {levelname:s} {name:s}.{funcName:s}: {message:s}",
            style="{",
        )
        self.root_logger_formatter.default_time_format = "%H:%M:%S"

        self.root_logger_stream_handler.setFormatter(self.root_logger_formatter)
        self.root_logger.addHandler(self.root_logger_stream_handler)
        self.root_logger.setLevel(1)  # actual level filtering is left to handlers

        self.get_logger("LoggingHelper").debug("Logging OK")

    def get_logger(self, name):
        log = self.root_logger.getChild(name)

        def trace(message, *args, **kwargs):
            if log.isEnabledFor(LoggingHelper.trace_level):
                log._log(LoggingHelper.trace_level, message, args, **kwargs)

        log.trace = trace

        def Logger_makeRecordWrapper(
            name, level, fn, lno, msg, args, exc_info, func=None, extra=None, sinfo=None
        ):
            name = name[len(__package__) + 1 :]
            self = log
            record = logging.Logger.makeRecord(
                self, name, level, fn, lno, msg, args, exc_info, func, sinfo
            )

            def LogRecord_getMessageNewStyleFormatting():
                self = record
                msg = str(self.msg)
                args = self.args
                if args:
                    if not isinstance(args, tuple):
                        args = (args,)
                    msg = msg.format(*args)
                return msg

            record.getMessage = LogRecord_getMessageNewStyleFormatting
            return record

        log.makeRecord = Logger_makeRecordWrapper
        return log

    def set_console_level(self, level):
        self.root_logger_stream_handler.setLevel(level)

    def set_log_file(self, path):
        if self.root_logger_file_handler is not None:
            self.root_logger.removeHandler(self.root_logger_file_handler)
            self.root_logger_file_handler = None
        if path is not None:
            self.root_logger_file_handler = logging.FileHandler(path, mode="w")
            self.root_logger_file_handler.setFormatter(self.root_logger_formatter)
            self.root_logger.addHandler(self.root_logger_file_handler)
            self.root_logger_file_handler.setLevel(1)


class AllocatorOutOfFreeRanges(Exception):
    pass


class Allocator:
    def __init__(self, free_ranges=None, tail_range_start=None):
        self.free_ranges = free_ranges if free_ranges else []
        self.tail_range_start = tail_range_start

    def alloc(self, size, align=1):
        assert size > 0
        assert align >= 1

        for i, (range_start, range_end) in enumerate(self.free_ranges):
            range_start_aligned = math.ceil(range_start / align) * align
            if (range_end - range_start_aligned) >= size:
                alloc_range_start = range_start_aligned
                alloc_range_end = alloc_range_start + size
                self.free_ranges.pop(i)
                if (alloc_range_start - range_start) > 0:
                    self.free_ranges.append((range_start, alloc_range_start))
                if (range_end - alloc_range_end) > 0:
                    self.free_ranges.append((alloc_range_end, range_end))
                return alloc_range_start, alloc_range_end

        if self.tail_range_start is None:
            raise AllocatorOutOfFreeRanges

        prev_tail_range_start = self.tail_range_start
        tail_range_start_aligned = math.ceil(prev_tail_range_start / align) * align
        alloc_range_start = tail_range_start_aligned
        alloc_range_end = alloc_range_start + size
        self.tail_range_start = alloc_range_end
        if (alloc_range_start - prev_tail_range_start) > 0:
            self.free_ranges.append((prev_tail_range_start, alloc_range_start))
        return alloc_range_start, alloc_range_end

    def alloc_range(self, start, end):
        i = 0
        while i < len(self.free_ranges):
            range_start, range_end = self.free_ranges[i]
            if start <= range_start:
                if end > range_start:
                    self.free_ranges.pop(i)
                    if range_end > end:
                        self.free_ranges.append((end, range_end))
                else:  # end <= range_start
                    i += 1
            else:  # start > range_start:
                if start < range_end:
                    self.free_ranges.pop(i)
                    self.free_ranges.append((range_start, start))
                    if range_end > end:
                        self.free_ranges.append((end, range_end))
                else:  # start >= range_end
                    i += 1

    def free(self, start, end):
        i = 0
        while i < len(self.free_ranges):
            range_start, range_end = self.free_ranges[i]
            if start <= range_start:
                if end >= range_start:
                    self.free_ranges.pop(i)
                    if range_end > end:
                        end = range_end
                else:  # end < range_start
                    i += 1
            else:  # start > range_start:
                if start <= range_end:
                    self.free_ranges.pop(i)
                    start = range_start
                    if range_end > end:
                        end = range_end
                else:  # start > range_end
                    i += 1
        self.free_ranges.append((start, end))

    def __str__(self):
        return "Free: {} Tail: {}".format(
            ",".join(
                "0x{:X}-0x{:X}".format(start, end) for start, end in self.free_ranges
            ),
            "None"
            if self.tail_range_start is None
            else "0x{:X}".format(self.tail_range_start),
        )

    def __repr__(self):
        return "Allocator(free_ranges={!r}, tail_range_start={!r})".format(
            self.free_ranges, self.tail_range_start
        )


def free_strings(
    allocator,  # type: Allocator
    ranges,  # type: List[Tuple]
    data,  # type: bytes
):
    """
    Mark as free the space used by the strings delimited by `ranges`,
    also detect and mark as free zero padding (alignment) between strings.

    The `ranges` argument will be sorted in-place
    """
    ranges.sort(key=lambda range: range[0])
    for i, (start, end) in enumerate(ranges):
        if i == 0:
            free_stride_start = start
            free_stride_end = end
        else:
            if (
                free_stride_end <= start
                and (start - free_stride_end) < 4
                and set(data[free_stride_end:start]).issubset({0})
            ):
                free_stride_end = end
            else:
                allocator.free(free_stride_start, free_stride_end)
                free_stride_start = start
                free_stride_end = end
    allocator.free(free_stride_start, free_stride_end)


dma_entry_struct = struct.Struct(">IIII")
assert dma_entry_struct.size == 0x10

u32_struct = struct.Struct(">I")
assert u32_struct.size == 4

rom_file_struct = struct.Struct(">II")
assert rom_file_struct.size == 8

leading_number = re.compile(r"^0*(0x[0-9a-fA-F]+|[1-9][0-9]*|0)")


class VersionInfo:
    def __init__(self, **kwargs):
        # TODO proper constructor and version info handling once stuff works
        self.__dict__.update(kwargs)


version_info_mq_debug = VersionInfo(
    dmaentry_index_makerom=0,
    dmaentry_index_boot=1,
    dmaentry_index_dmadata=2,
    dmaentry_index_audiobank=3,
    dmaentry_index_audioseq=4,
    dmaentry_index_audiotable=5,
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
        moveable_rom=False,
        moveable_vrom=False,
    ):
        self.data = data
        self.dma_entry = dma_entry
        self.moveable_rom = moveable_rom
        self.moveable_vrom = moveable_vrom


class RomFileEditable(RomFile):
    def __init__(self, rom_file, resizable):
        self.data = bytearray(rom_file.data)
        self.dma_entry = rom_file.dma_entry
        self.moveable_rom = rom_file.moveable_rom
        self.moveable_vrom = rom_file.moveable_vrom
        self.resizable = resizable
        self.allocator = Allocator(None, len(self.data) if resizable else None)


class ROM:
    def __init__(
        self,
        version_info,  # type: VersionInfo
        data,  # type: bytes
        files,  # type: List[RomFile]
        logging_helper=None,  # type: Optional[LoggingHelper]
    ):
        self.log = None if logging_helper is None else logging_helper.get_logger("ROM")

        self.version_info = version_info
        self.data = data

        self.file_makerom = files[self.version_info.dmaentry_index_makerom]

        self.file_boot = files[
            self.version_info.dmaentry_index_boot
        ]  # type: RomFileEditable
        assert type(self.file_boot) == RomFileEditable

        self.file_dmadata = files[self.version_info.dmaentry_index_dmadata]

        self.file_code = RomFileEditable(
            files[self.version_info.dmaentry_index_code], False
        )
        files[self.version_info.dmaentry_index_code] = self.file_code

        self.files = files

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
                    yield (unaccounted_strand_start, i)
            prev_is_unaccounted = is_unaccounted[i]
            i += 1

        if prev_is_unaccounted:
            yield (unaccounted_strand_start, rom_size)

    def find_file_by_vrom(self, vrom):
        matching_files = [
            file
            for file in self.files
            if vrom >= file.dma_entry.vrom_start and vrom < file.dma_entry.vrom_end
        ]
        assert len(matching_files) == 1
        return matching_files[0]

    def new_file(self, data, name=None):
        dma_entry = DmaEntry(None, None, None, None, name)
        rom_file = RomFile(data, dma_entry, True, True)
        self.files.append(rom_file)
        return rom_file

    def realloc_moveable_vrom(self, move_vrom):
        # tag moveable files in vrom
        if move_vrom:
            moveable_vrom = set(file for file in self.files if file.moveable_vrom)
        else:
            moveable_vrom = set(
                file
                for file in self.files
                if file.moveable_vrom and file.dma_entry.vrom_start is None
            )

        # OoT's `DmaMgr_SendRequestImpl` limits the vrom to 64MB
        # https://github.com/zeldaret/oot/blob/f1d27bf6531fd6579d09dcf3078ee97c57b6fff1/src/boot/z_std_dma.c#L1864
        max_vrom = 0x4000000  # 64MB

        self.realloc_vrom(max_vrom, moveable_vrom)

    def realloc_vrom(self, max_vrom, moveable_vrom):
        # find strands where vrom isn't taken by an "immoveable vrom file"
        vrom_allocator = Allocator()
        vrom_allocator.free(0, max_vrom)

        for file in self.files:
            if file not in moveable_vrom:
                vrom_start = file.dma_entry.vrom_start
                vrom_end = file.dma_entry.vrom_end
                vrom_allocator.alloc_range(vrom_start, vrom_end)
                # the vrom offsets of this file won't be updated,
                # check now if the file fits the reserved vrom
                assert len(file.data) == (vrom_end - vrom_start)

        if self.log is not None:
            self.log.debug(
                "After allocating immovable files: vrom_allocator = {}", vrom_allocator
            )

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

        if self.log is not None:
            self.log.trace("Reallocating vrom for vrom-moveable files")
        # fit moveable vrom files in the space highlighted by dynamic_vrom_ranges,
        # shrinking those ranges as we go
        for file in moveable_vrom_sorted:
            # TODO is 16-align needed for vrom?
            start, end = vrom_allocator.alloc(len(file.data), 0x10)
            file.dma_entry.vrom_start = start
            file.dma_entry.vrom_end = end
            if self.log is not None:
                self.log.trace("VROM> {}", file.dma_entry)

    def realloc_moveable_rom(self, move_rom):
        if move_rom:
            moveable_rom = set(file for file in self.files if file.moveable_rom)
        else:
            moveable_rom = set(
                file
                for file in self.files
                if file.moveable_rom and file.dma_entry.rom_start is None
            )

        # TODO is max_rom limited by anything apart from max_vrom to prevent eg a 128MB rom?
        max_rom = 0x4000000  # 64MB

        self.realloc_rom(max_rom, moveable_rom)

    def realloc_rom(self, max_rom, moveable_rom):
        # find strands where rom isn't taken by an "immoveable rom file"
        rom_allocator = Allocator()
        rom_allocator.free(0, max_rom)

        for file in self.files:
            if file not in moveable_rom:
                rom_allocator.alloc_range(
                    file.dma_entry.rom_start,
                    file.dma_entry.rom_start + len(file.data),
                )

        if self.log is not None:
            self.log.debug(
                "After allocating immovable files: rom_allocator = {}", rom_allocator
            )

        # sort files from largest to smallest
        moveable_rom_sorted = list(moveable_rom)
        # TODO see the vrom equivalent moveable_vrom_sorted
        moveable_rom_sorted.sort(
            key=lambda file: (len(file.data), file.dma_entry.name),
            reverse=True,
        )

        if self.log is not None:
            self.log.trace("Reallocating rom for rom-moveable files")
        # fit moveable rom files in the space highlighted by dynamic_rom_ranges,
        # shrinking those ranges as we go
        for file in moveable_rom_sorted:
            start, end = rom_allocator.alloc(len(file.data), 0x10)
            file.dma_entry.rom_start = start
            file.dma_entry.rom_end = 0  # TODO ?
            if self.log is not None:
                self.log.trace("ROM> {}", file.dma_entry)


class ROMReader:
    def __init__(
        self,
        version_info,
        logging_helper=None,  # type: Optional[LoggingHelper]
    ):
        self.log = (
            None if logging_helper is None else logging_helper.get_logger("ROMReader")
        )

        self.version_info = version_info

    def read(self, data):
        dma_entries, file_boot = self.parse_dma_table(data)

        files = []  # type: List[RomFile]
        for dma_entry in dma_entries:
            rom_end = dma_entry.rom_start + (dma_entry.vrom_end - dma_entry.vrom_start)
            romfile = RomFile(
                data[dma_entry.rom_start : rom_end],
                dma_entry,
            )
            files.append(romfile)

        files[self.version_info.dmaentry_index_boot] = file_boot

        rom = ROM(self.version_info, data, files)

        # TODO can all other files really move?
        for file in rom.files:
            file.moveable_rom = True

        rom.file_makerom.moveable_rom = False
        rom.file_boot.moveable_rom = False
        rom.file_dmadata.moveable_rom = False

        # TODO these audio files can move if the rom pointers in code are updated accordingly
        # https://github.com/zeldaret/oot/blob/bf0f26db9b9c2325cea249d6c8e0ec3b5152bcd6/src/code/audio_load.c#L1109
        rom.files[self.version_info.dmaentry_index_audiobank].moveable_rom = False
        rom.files[self.version_info.dmaentry_index_audioseq].moveable_rom = False
        rom.files[self.version_info.dmaentry_index_audiotable].moveable_rom = False

        return rom

    def parse_dma_table(self, data):
        # type: (bytes) -> Tuple[List[DmaEntry], RomFileEditable]

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

        boot_dma_entry_temp = DmaEntry(
            boot_vrom_start,
            boot_vrom_end,
            boot_rom_start,
            boot_rom_end,
        )

        boot_rom_end = boot_rom_start + (boot_vrom_end - boot_vrom_start)
        assert boot_rom_end <= len(data)

        file_boot = RomFileEditable(
            RomFile(data[boot_rom_start:boot_rom_end], boot_dma_entry_temp), False
        )

        filename_boot_offset_ranges = []

        def get_filename(i):
            (filename_vram_start,) = u32_struct.unpack_from(
                file_boot.data,
                self.version_info.dma_table_filenames_boot_offset + i * u32_struct.size,
            )
            filename_boot_offset_start = (
                filename_vram_start - self.version_info.boot_vram_start
            )
            assert filename_boot_offset_start < len(file_boot.data)
            filename_boot_offset_end = filename_boot_offset_start
            while file_boot.data[filename_boot_offset_end] != 0:
                filename_boot_offset_end += 1
                assert filename_boot_offset_end < len(file_boot.data)
                assert (filename_boot_offset_end - filename_boot_offset_start) < 100

            filename_boot_offset_ranges.append(
                (filename_boot_offset_start, filename_boot_offset_end + 1)
            )

            return file_boot.data[
                filename_boot_offset_start:filename_boot_offset_end
            ].decode("ascii")

        if self.log is not None:
            self.log.trace("Parsed DMA table:")

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
                if self.log is not None:
                    self.log.trace("{:04} {}", dmaentry_index, dmaentry)

            dmaentry_rom_start += dma_entry_struct.size
            dmaentry_index += 1

        file_boot.dma_entry = dma_entries[self.version_info.dmaentry_index_boot]

        free_strings(file_boot.allocator, filename_boot_offset_ranges, file_boot.data)
        if self.log is not None:
            self.log.debug("file_boot.allocator = {}", file_boot.allocator)

        return dma_entries, file_boot


class ROMPacker:
    def __init__(
        self,
        rom,  # type: ROM
        logging_helper=None,  # type: Optional[LoggingHelper]
    ):
        self.log = (
            None if logging_helper is None else logging_helper.get_logger("ROMPacker")
        )

        self.rom = rom

        self.filenames_vram_start = dict()  # type: Dict[str, int]

    def pack_boot_alloc_filenames(self):
        rom = self.rom

        for i, file in enumerate(rom.files):
            dma_entry = file.dma_entry
            name = dma_entry.name  # type: str

            if name is None:
                # TODO not sure about how/where to handle default name
                name = "#{}".format(i)
                dma_entry.name = name

            if name in self.filenames_vram_start:
                continue

            (
                filename_boot_offset_start,
                filename_boot_offset_end,
            ) = rom.file_boot.allocator.alloc(len(name) + 1)
            rom.file_boot.data[filename_boot_offset_start:filename_boot_offset_end] = (
                name.encode("ascii") + b"\x00"
            )
            filename_vram_start = (
                rom.version_info.boot_vram_start + filename_boot_offset_start
            )
            self.filenames_vram_start[name] = filename_vram_start

    def pack_boot_filenames(self):
        rom = self.rom

        for i, file in enumerate(rom.files):
            dma_entry = file.dma_entry
            # update filename in the boot file array
            filename_vram_start = self.filenames_vram_start[dma_entry.name]
            u32_struct.pack_into(
                rom.file_boot.data,
                rom.version_info.dma_table_filenames_boot_offset + i * u32_struct.size,
                filename_vram_start,
            )

    def pack_dma_table(self):
        rom = self.rom

        assert rom.file_makerom == rom.files[rom.version_info.dmaentry_index_makerom]
        assert rom.file_boot == rom.files[rom.version_info.dmaentry_index_boot]
        assert rom.file_dmadata == rom.files[rom.version_info.dmaentry_index_dmadata]
        assert rom.file_code == rom.files[rom.version_info.dmaentry_index_code]

        dmadata_data = bytearray(len(rom.file_dmadata.data))
        if self.log is not None:
            self.log.trace("Built DMA table:")
        for i, file in enumerate(rom.files):
            dma_entry = file.dma_entry
            if self.log is not None:
                self.log.trace(dma_entry)
            dma_entry_struct.pack_into(
                dmadata_data,
                i * dma_entry_struct.size,
                dma_entry.vrom_start,
                dma_entry.vrom_end,
                dma_entry.rom_start,
                dma_entry.rom_end,
            )
        rom.file_dmadata.data = dmadata_data

    def write(
        self,
        out,  # type: io.IOBase
    ):
        rom = self.rom

        rom_data = bytearray(
            max(file.dma_entry.rom_start + len(file.data) for file in rom.files)
        )
        if self.log is not None:
            self.log.debug("Written ROM size: {:X}", len(rom_data))
        for file in rom.files:
            rom_data[
                file.dma_entry.rom_start : file.dma_entry.rom_start + len(file.data)
            ] = file.data
        out.write(rom_data)


class ModuleInfo:
    def __init__(
        self,
        task,  # type: str
        register,  # type: Callable[[PyRTInterface],None]
        task_dependencies=frozenset(),  # type: Set[str]
        description="",  # type: str
    ):
        self.task = task
        self.register = register
        self.task_dependencies = task_dependencies
        assert type(self.task_dependencies) in {set, frozenset}
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


EVENT_PARSE_ROM = PyRTEvent(
    "Parse ROM",
    "Find which files are what (eg scene or overlay), "
    "after the dma table was parsed and the ROM split into files.",
)

EVENT_DUMP_FILES = PyRTEvent(
    "Dump files",
    "Write out files into an organized tree, outside of the ROM.",
)

EVENT_LOAD_FILES = PyRTEvent(
    "Load files",
    "Read files from a directory tree outside of the ROM.",
)

EVENT_PACK_ROM_BEFORE_FILE_ALLOC = PyRTEvent(
    "Pack ROM (before file alloc)",
    "Pack various data into files (before the file offsets in VROM/ROM get updated). "
    "At this point ROM/VROM offsets are invalid, and files may be resized.",
)

EVENT_PACK_ROM_AFTER_FILE_ALLOC = PyRTEvent(
    "Pack ROM (after file alloc)",
    "Pack various data into files (after the file offsets in VROM/ROM get updated). "
    "At this point ROM/VROM offsets are final, and files cannot be resized.",
)


class PyRTInterface:
    def __init__(
        self,
        logging_helper,  # type: LoggingHelper
    ):
        self.logging_helper = logging_helper
        self.log = logging_helper.get_logger("PyRTInterface")

        self.rom = None  # type: ROM
        self.modules = []  # type: List[ModuleType]

        # module-specific usage, key should be ModuleInfo#task
        # and value some instance-specific module data
        self.modules_data = {}  # type: Dict[str, Any]

        self.event_listeners = (
            dict()
        )  # type: Dict[PyRTEvent, List[Callable[[PyRTInterface],None]]]
        self.can_add_event_listeners = False

    def set_rom(self, rom):
        self.rom = rom

    def load_modules(self):
        import importlib

        log = self.log

        modules_dir_path = os.path.dirname(__file__)
        log.debug("Looking for modules in {}", modules_dir_path)
        log.debug("__package__ = {}", __package__)

        module_names_by_task = dict()

        with os.scandir(modules_dir_path) as dir_iter:
            for dir_entry in dir_iter:
                # skip __pycache__ and __init__.py more explicitly
                if dir_entry.name.startswith("_"):
                    log.debug("Skipping {} (_ prefix)", dir_entry.path)
                    continue
                if not dir_entry.is_file():
                    log.warn("Skipping {} (not a file)", dir_entry.path)
                    continue
                if not dir_entry.name.endswith(".py"):
                    log.warn("Skipping {} (not a .py file)", dir_entry.path)
                    continue
                module_name = dir_entry.name[: -len(".py")]
                log.debug("Loading {}", module_name)
                module = importlib.import_module("." + module_name, __package__)
                if not hasattr(module, "pyrt_module_info"):
                    log.warn("Skipping module {} (no pyrt_module_info)", module_name)
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
        log = self.log

        registered_modules = dict()  # type: Dict[str, ModuleType]
        unregistered_modules = {
            module.pyrt_module_info.task: module for module in self.modules
        }  # type: Dict[str, ModuleType]

        while unregistered_modules:
            # find a module with no unregistered dependency
            registerable_module_item = next(
                (
                    (module_task, module)
                    for module_task, module in unregistered_modules.items()
                    if module.pyrt_module_info.task_dependencies.isdisjoint(
                        unregistered_modules.keys()
                    )
                ),
                None,
            )
            if registerable_module_item is None:
                raise Exception(
                    "Can't solve dependencies for remaining modules: "
                    + repr(unregistered_modules)
                )
            module_task, module = registerable_module_item
            if not module.pyrt_module_info.task_dependencies.issubset(
                registered_modules.keys()
            ):
                raise Exception(
                    "Module "
                    + repr(module.pyrt_module_info)
                    + " has unknown dependencies "
                    + str(
                        module.pyrt_module_info.task_dependencies.difference(
                            registered_modules.keys()
                        )
                    )
                )
            module_info = module.pyrt_module_info  # type: ModuleInfo

            log.debug("Registering module {!r}", module_info)

            # Only allow adding event listeners on module registration.
            # Since modules are registered in dependency order, and event
            # listeners callbacks are called in the order they were
            # registered in, this ensures calling event listeners callbacks
            # in the correct order with respect to dependencies.
            self.can_add_event_listeners = True
            module_info.register(self)
            self.can_add_event_listeners = False

            del unregistered_modules[module_task]
            registered_modules[module_task] = module

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
        self.log.debug("Raising {}", event)
        for callback in self.event_listeners[event]:
            try:
                callback(self)
            except Exception:
                self.log.fatal("An error ocurred raising event {!r}", event)
                raise

    def add_event_listener(
        self,
        event,  # type: PyRTEvent
        callback,  # type: Callable[[PyRTInterface],None]
    ):
        if not self.can_add_event_listeners:
            raise Exception("Cannot add event listeners at this time.")
        event_listeners = self.event_listeners.get(event)
        if event_listeners is None:
            self.log.debug("self.event_listeners =", repr(self.event_listeners))
            self.log.debug("id(event) =", id(event))
            self.log.debug(
                "id(self.event_listeners.keys()) =",
                [id(ev) for ev in self.event_listeners],
            )
            raise ValueError("Event not registered: " + repr(event))
        event_listeners.append(callback)


def main():
    logging_helper = LoggingHelper("pyrt")
    logging_helper.set_log_file("log.txt")
    logging_helper.set_console_level(logging.INFO)
    log = logging_helper.get_logger(__name__)

    pyrti = PyRTInterface(logging_helper)

    pyrti.register_event(EVENT_PARSE_ROM)
    pyrti.register_event(EVENT_DUMP_FILES)
    pyrti.register_event(EVENT_LOAD_FILES)
    pyrti.register_event(EVENT_PACK_ROM_BEFORE_FILE_ALLOC)
    pyrti.register_event(EVENT_PACK_ROM_AFTER_FILE_ALLOC)

    log.info("Loading modules...")
    pyrti.load_modules()

    log.info("Registering modules...")
    pyrti.register_modules()

    log.info("Reading ROM...")
    with open("oot-mq-debug.z64", "rb") as f:
        data = f.read()

    version_info = version_info_mq_debug
    rom_reader = ROMReader(version_info, logging_helper)

    rom = rom_reader.read(data)

    find_unaccounted = False
    if find_unaccounted:
        log.info("Unaccounted ROM ranges in the input ROM:")
        log.info(
            ",".join(
                "0x{:08X}-0x{:08X}({})".format(
                    start,
                    end,
                    ",".join(
                        "0" if v == 0 else "0x{:X}".format(v)
                        for v in set(data[start:end])
                    ),
                )
                for start, end in rom.find_unaccounted(rom.data)
            )
        )

    pyrti.set_rom(rom)

    pyrti.raise_event(EVENT_PARSE_ROM)

    pyrti.raise_event(EVENT_DUMP_FILES)

    pyrti.raise_event(EVENT_LOAD_FILES)

    rom_packer = ROMPacker(rom, logging_helper)

    rom_packer.pack_boot_alloc_filenames()
    pyrti.raise_event(EVENT_PACK_ROM_BEFORE_FILE_ALLOC)

    move_vrom = True
    move_rom = True

    rom.realloc_moveable_vrom(move_vrom)
    rom.realloc_moveable_rom(move_rom)

    rom_packer.pack_boot_filenames()
    rom_packer.pack_dma_table()
    pyrti.raise_event(EVENT_PACK_ROM_AFTER_FILE_ALLOC)

    log.info("Writing ROM...")
    with open("oot-build.z64", "wb") as f:
        rom_packer.write(f)

    log.info("Done!")
