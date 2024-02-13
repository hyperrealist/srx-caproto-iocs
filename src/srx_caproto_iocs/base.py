from __future__ import annotations

import threading
import uuid
from enum import Enum
from pathlib import Path

from caproto import ChannelType
from caproto.server import PVGroup, pvproperty

from .utils import now


class AcqStatuses(Enum):
    """Enum class for acquisition statuses."""

    IDLE = "Done"
    ACQUIRING = "Count"


class StageStates(Enum):
    """Enum class for stage states."""

    UNSTAGED = "unstaged"
    STAGED = "staged"


class GenericSaveIOC(PVGroup):
    """Generic Caproto Save IOC"""

    write_dir = pvproperty(
        value="/tmp",
        doc="The directory to write data to. It support datetime formatting, e.g. '/tmp/det/%Y/%m/%d/'",
        string_encoding="utf-8",
        report_as_string=True,
        max_length=255,
    )
    file_name = pvproperty(
        value="test.h5",
        doc="The file name of the file to write to. It support <str>.format() based formatting, e.g. 'scan_{num:06d}.h5'",
        string_encoding="utf-8",
        report_as_string=True,
        max_length=255,
    )
    full_file_path = pvproperty(
        value="",
        doc="Full path to the data file",
        dtype=str,
        read_only=True,
        max_length=255,
    )

    # TODO: check non-negative value in @frame_num.putter.
    frame_num = pvproperty(value=0, doc="Frame counter", dtype=int)

    stage = pvproperty(
        value=StageStates.UNSTAGED.value,
        enum_strings=[x.value for x in StageStates],
        dtype=ChannelType.ENUM,
        doc="Stage/unstage the detector",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._request_queue = None
        self._response_queue = None

    _queue = pvproperty(value=0, doc="A PV to facilitate threading-based queue")

    @_queue.startup
    async def _queue(self, instance, async_lib):
        """The startup behavior of the count property to set up threading queues."""
        # pylint: disable=unused-argument
        self._request_queue = async_lib.ThreadsafeQueue()
        self._response_queue = async_lib.ThreadsafeQueue()

        # Start a separate thread that consumes requests and sends responses.
        thread = threading.Thread(
            target=self.saver,
            daemon=True,
            kwargs={
                "request_queue": self._request_queue,
                "response_queue": self._response_queue,
            },
        )
        thread.start()

    @stage.putter
    async def stage(self, instance, value):
        """The stage method to perform preparation of a dataset to save the data."""
        if (
            instance.value in [True, StageStates.STAGED.value]
            and value == StageStates.STAGED.value
        ):
            msg = "The device is already staged. Unstage it first."
            print(msg)
            return False

        if value == StageStates.STAGED.value:
            # Steps:
            # 1. Render 'write_dir' with datetime lib and replace any blank spaces with underscores.
            # 2. Render 'file_name' with .format().
            # 3. Replace blank spaces with underscores.

            date = now(as_object=True)
            write_dir = Path(date.strftime(self.write_dir.value).replace(" ", "_"))
            if not write_dir.exists():
                msg = f"Path '{write_dir}' does not exist."
                print(msg)
                return False

            file_name = self.file_name.value
            uid = "" if "{uid" not in file_name else str(uuid.uuid4())
            full_file_path = write_dir / file_name.format(
                num=self.frame_num.value, uid=uid
            )
            full_file_path = str(full_file_path)
            full_file_path.replace(" ", "_")

            print(f"{now()}: {full_file_path = }")

            await self.full_file_path.write(full_file_path)

            return True

        return False

    @staticmethod
    def saver(request_queue, response_queue):
        """The saver callback for threading-based queueing."""
        while True:
            received = request_queue.get()
            filename = received["filename"]
            data = received["data"]
            try:
                # save_hdf5(fname=filename, data=data)
                print(f"{now()}: saved {data.shape} data into:\n  {filename}")

                success = True
                error_message = ""
            except Exception as exc:  # pylint: disable=broad-exception-caught
                # The GeRM detector happens to response twice for a single
                # ".CNT" put, so capture an attempt to save the file with the
                # same name here and do nothing.
                success = False
                error_message = exc
                print(
                    f"Cannot save file {filename!r} due to the following exception:\n{exc}"
                )

            response = {"success": success, "error_message": error_message}
            response_queue.put(response)