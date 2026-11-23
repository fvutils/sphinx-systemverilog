"""The pyslang front end: SystemVerilog sources to svdb records.

:mod:`.emit` turns the object model that :class:`~..model.builder.ModelBuilder`
produces into records (plan D2-IMPL-1); :mod:`.build` runs the whole front end
into a database file and keeps the per-project cache (D2-IMPL-3).
"""
