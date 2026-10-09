"""Validate destinations and stage related outputs before publishing."""
from contextlib import contextmanager
from pathlib import Path
import os
import tempfile


def distinct_paths(inputs, outputs):
    inputs = {Path(path).resolve() for path in inputs}
    outputs = [Path(path).resolve() for path in outputs]
    if len(set(outputs)) != len(outputs) or inputs.intersection(outputs):
        raise ValueError('Output paths must differ from all inputs and each other')


@contextmanager
def staged_outputs(destinations):
    """Nothing is published until all writers/checks finish successfully.

    Each replacement is atomic; the collection is not a filesystem transaction.
    """
    destinations = [Path(path).resolve() for path in destinations]
    stages = []
    try:
        for destination in destinations:
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='.' + destination.stem + '-', suffix=destination.suffix,
                                        dir=destination.parent)
            os.close(fd)
            stages.append(Path(name))
        yield stages
        for stage, destination in zip(stages, destinations):
            os.replace(stage, destination)
    finally:
        for stage in stages:
            stage.unlink(missing_ok=True)
