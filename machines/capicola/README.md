# Historical Capicola experiments

This directory holds the earlier analyzed-keyframe, preparation/cache, quality
and source-playback experiments. It is not the author engine used by the current
OS packages. That source is in [capicola-reddit](../capicola-reddit/README.md).

These sources, licenses and frozen contracts remain for explicit historical
checks and older low-level mod fixtures. `./labctl unit capicola-history` selects
their tests; the ordinary `capicola` suite covers the current port and shared
helpers. The normal OS packager no longer offers these older engine choices.

Do not infer the active implementation from an old R1/R2/R3 name. Use
[the current guide](../../docs/CAPICOLA.md) for the source and build map.
