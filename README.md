# etl_framework

A composable, operator-overloaded pandas ETL and data-pipeline construction library — you build pipelines by writing expressions like `Column('fare') * 1.1`, not by wiring up tasks in a DAG.

## Status

This library was built ~2021–2022 while working on a telco data platform, as an internal tool for constructing high-volume batch data pipelines (CSV, binary switch records, ASN.1-encoded billing records). It is being published here as a portfolio piece to show the design, **not** as an actively maintained open-source project. There is no roadmap, no issue triage, and no guarantee of future updates — treat it as a snapshot of a real, working piece of infrastructure rather than a supported package. It has been updated for pandas 2.x compatibility and had employer-specific content removed prior to publishing, but otherwise reflects the code as it was written on the job.

## Philosophy

Most Python ETL/pipeline tools fall into one of two camps: an orchestrator that schedules a DAG of opaque tasks (Airflow, Prefect, Dagster), or a thin wrapper around "just write a function." This library takes a different approach entirely: **a pipeline is a single composed object built entirely from operator overloading, with no executor or scheduler underneath it.**

The base class, `Operation` (`etl_framework/operations/base.py`), overloads:

- `>>` — chain operations sequentially (output of the left becomes input of the right), auto-flattening nested chains into one `ChainedOperations`
- `&`, `|`, `~` — boolean-style combination and inversion
- `+ - * / // % **` — arithmetic, elementwise on vectors or scalar
- `> < == != >= <=` — comparisons, producing boolean masks
- `[]` — slicing (including vectorised string slicing on a `pd.Series`)

The result is that pipeline code reads like the pandas expression it represents:

```python
Column('vendor_id') > 0
(Column('a') > 0) & (Column('b') < 10)
(Column('dropoff_timestamp') - Column('pickup_timestamp')) >> TimedeltaToSeconds()
```

...while remaining **lazy, composable and introspectable** rather than eagerly evaluated. Every operator call just builds a small tree of `Operation` objects; nothing runs until the resulting object is called with an input. A raw Python value or plain function dropped into that expression is auto-wrapped as a `Value` or `Lambda` operation by `convert_to_operation()`, so scalars and callables compose transparently alongside `Operation` instances.

Because every node in a pipeline is a plain object (not a string reference into a workflow engine's task graph), the framework gets several capabilities essentially for free — most notably built-in profiling and visualization (see [Core concepts](#core-concepts) below) that apply uniformly to *any* pipeline, however it's composed, without additional instrumentation.

## Installation

Not published to PyPI. Install from a clone in editable mode:

```bash
git clone <repo-url>
cd etl_framework
pip install -e ".[dev]"
```

Optional extras (from `pyproject.toml`), combine as needed, e.g. `pip install -e ".[dev,viz]"`:

| Extra | Adds | Unlocks |
|---|---|---|
| `dev` | `pytest` | Running the test suite |
| `viz` | `pydot`, `snakeviz` | `show_graph()` pipeline visualization and `profile_snakeviz()` profiling UI |
| `crypto` | `pycryptodome` | AES encrypt/decrypt operations (`etl_framework/operations/cryptography.py`) |
| `hdfs` | `hdfs` | `HDFSFileSystemWriter` |
| `cython-experiments` | `Cython` | The experimental Cython-accelerated ASN.1 BER decoder |
| `numba-experiments` | `numba` | The experimental Numba-accelerated ASN.1 BER decoder |

Core runtime dependencies are just `pandas`, `numpy`, `pytz`, and `python-dateutil`. Requires Python 3.8+.

## Quickstart

This walks through the pipeline built in `Demo.ipynb` over the public [NYC TLC Yellow Taxi trip data](https://www1.nyc.gov/site/tlc/about/tlc-trip-record-data.page) — extract typed columns from a CSV, clean and derive new columns, then profile the whole thing. See the notebook for the full walkthrough with live output.

**Extract** a typed DataFrame directly from the CSV — each `Field` declares its own dtype/parsing, so there's no separate `read_csv()` + coercion step:

```python
from etl_framework.operations.io import LocalFileReader
from etl_framework.operations.pandas.record_extractors.delimited import (
    DelimitedRecordExtractor, NumberField, TimestampField, IntegerField, StringField,
)

record_extractor = DelimitedRecordExtractor(
    fields=[
        IntegerField('vendor_id', column_id='VendorID', size=8),
        TimestampField('pickup_timestamp', column_id='tpep_pickup_datetime'),
        TimestampField('dropoff_timestamp', column_id='tpep_dropoff_datetime'),
        IntegerField('passenger_count', size=8),
        NumberField('distance', column_id='trip_distance'),
        IntegerField('pickup_location_id', column_id='PULocationID'),
        IntegerField('dropoff_location_id', column_id='DOLocationID'),
        IntegerField('payment_type', size=8),
        NumberField('fare_amount'),
        NumberField('tip_amount'),
        NumberField('congestion_surcharge'),
    ],
)
read_extract_records = LocalFileReader() >> record_extractor

df = read_extract_records('data/yellow_tripdata_2021-01.csv')
```

**Transform** — drop bad rows, derive a duration column, apply a conditional 10% card-payment surcharge, and compute a derived rate, all as composed `Operation`s:

```python
from etl_framework.operations.pandas import DropRows, Column, IsNull, TimedeltaToSeconds, SetColumn, DFWhere

remove_bad_data = DropRows((Column('vendor_id') >> IsNull()) | (Column('passenger_count') == 0))

calculate_duration = SetColumn(
    'trip_duration',
    (Column('dropoff_timestamp') - Column('pickup_timestamp')) >> TimedeltaToSeconds(),
)

add_card_surcharge = DFWhere(
    Column('payment_type') == 2,
    SetColumn('fare_amount', Column('fare_amount') * 1.1),
)

calculate_cost_per_passenger_per_minute = SetColumn(
    'cost_per_passenger_per_minute',
    (Column('fare_amount') + Column('tip_amount')) / (Column('passenger_count') * Column('trip_duration') / 60),
)

transforms = remove_bad_data >> calculate_duration >> add_card_surcharge >> calculate_cost_per_passenger_per_minute
```

**Run and profile** the whole thing, extraction included, end to end:

```python
full_pipeline = read_extract_records >> transforms
full_pipeline.profile_snakeviz('data/yellow_tripdata_2021-01.csv')  # opens a SnakeViz flame graph in Jupyter
```

`add_card_surcharge` deliberately uses `DFWhere` rather than a plain `df.loc[mask, 'fare_amount'] *= 1.1` — see [Core concepts](#core-concepts) for why that matters beyond style.

## Core concepts

**Operator-based chaining.** `>>` is the pipeline backbone: `a >> b >> c` builds a single `ChainedOperations` (flattening automatically, so chaining a chain doesn't nest), which calls each stage in order, passing output to input. Any pipeline is itself just an `Operation`, so it can be embedded inside a larger one.

**`Column` / `SetColumn`.** `Column('x')` is an `Operation` that extracts column `'x'` from whatever DataFrame or Series it's called with; it participates in arithmetic and comparisons like any other operation. `SetColumn('y', <transform>)` runs `<transform>` against the input DataFrame and assigns the resulting Series onto (new or existing) column `'y'`, returning a new DataFrame with a shallow copy semantics.

**`DFWhere` / `SeriesWhere` and `get_required_columns()`.** These conditionally apply a wrapped operation to only the rows matching a boolean mask, then integrate the result back into the original data. `DFWhere` (the DataFrame version) is genuinely optimized, not just a convenience wrapper: `DataframeOperation` subclasses (`Column`, `SetColumn`, `DropColumns`, `Merge`, etc., in `etl_framework/operations/pandas/base.py`) each implement `get_required_columns()`, and `DFWhere` walks the operation tree it wraps (via `Operation.search()`) to automatically infer exactly which columns the wrapped transform needs and which it changes. It then slices the DataFrame down to only those columns before masking and copying, instead of copying the whole frame — a meaningful performance/memory win on wide DataFrames, derived directly from the pipeline's own structure rather than hand-tuned. `DFWhere` explicitly refuses to wrap `DropRows`, `DropColumns`, `RenameColumns`, or `Explode` (raising `InvalidOperationError`), since row/column-dropping operations inside it would break the masking/reintegration strategy.

**Extractor → transforms → writer.** The idiomatic shape of a full pipeline is `Extractor >> transform_operations >> Writer`. Extractors turn raw bytes/text into a typed `DataFrame`; transforms are ordinary composed `Operation`s; writers/exporters send the result somewhere.

**Built-in observability.** Every `Operation` carries its own execution profiling — `enable_profiling()` / `disable_profiling()` toggle a custom cProfile-like recorder that tracks call counts and cumulative/self time *per operation instance*, correctly attributing time to whichever specific parent invoked a shared child operation (something a standard flat profiler can't do, since it only tracks time per function, not per position in a call graph). `profile_snakeviz(input)` runs the pipeline under this profiler and opens the result in [SnakeViz](https://jiffyclub.github.io/snakeviz/) inside a Jupyter notebook, using pstats-compatible output. Separately, `show_graph()` renders the pipeline's structure as a Graphviz diagram (via `pydot`), useful for seeing the shape of a deeply chained or forked pipeline at a glance. Both require the `viz` extra.

## Operation catalogue

Grouped by module, not exhaustive — see docstrings in source for full parameter details.

**Core / generic** (`etl_framework/operations/{general,control,logical,conditional,wrappers}.py`)

| Operation | Purpose |
|---|---|
| `Value`, `Lambda`, `Pass` | Wrap a constant, a plain callable, or a no-op into an `Operation` |
| `ChainedOperations` | The result of `>>` chaining; also constructible directly |
| `If`, `SwitchCase` | Branch on a condition or a mapped key |
| `Fork`, `CollectFrom`, `Map` | Run multiple chains on one input; collect/iterate a sequence |
| `MapValue`, `GetAttr`, `Filter`, `Length` | General value mapping/attribute access/filtering |
| `CallMethod` | Call an (optionally dotted) method on the input object |
| `ContextValue` | Pull a value from the ambient transform context dict |
| `Print`, `RaiseException` | Debugging / explicit failure |
| `In`, `Is`, `And`, `Or`, `Not` | Operations backing `in`/`is`/boolean logic (since those Python operators can't be overloaded to stay lazy) |
| `StringContains`, `StringIsNumeric`, `IsInstance` | Scalar string/type checks |
| `Cached`, `MapArguments` | Memoize a scalar transform; build multi-arg calls from one input |

**Pandas column/value operations** (`etl_framework/operations/pandas/{general,conditional}.py`)

| Operation | Purpose |
|---|---|
| `Column` | Select a column from a DataFrame or a field from a row Series |
| `MapColumnValues`, `ColumnOfValue`, `FillNA` | Value mapping, constant column, NA filling |
| `Min` / `Max` | Row-wise or column-wise min/max |
| `Copy`, `PrintDF` | Defensive copy; debug-print a DataFrame |
| `IsIn`, `IsNull`, `IsEmpty`, `StringContains`, `StartsWith`, `IsNumeric`, `FieldExists` | Boolean-mask-producing column conditions |
| `MergeRowValues` | Combine several row fields with a custom merge/filter function |

**DataFrame-level operations** (`etl_framework/operations/pandas/dataframe.py`)

| Operation | Purpose |
|---|---|
| `DropRows`, `DropColumns`, `RenameColumns`, `Sort` | Standard row/column manipulation |
| `MultipleFillNA`, `Explode` | Bulk NA fill; explode list-like column into rows |
| `Combine`, `CombineFirst` | Elementwise / first-non-null combination of two columns |
| `SelectColumns`, `AlignCategories` | Column projection/ordering; align categorical dtypes |
| `Merge` | Join two DataFrames — validates that join-column dtypes actually match before merging, raising a clear `TypeError` instead of a confusing downstream failure |
| `CreateDuplicateRows` | Duplicate rows matching a condition |

**Pipeline-construction operations** (`etl_framework/operations/pandas/constructors.py`)

| Operation | Purpose |
|---|---|
| `SetColumn`, `ConvertColumn` | Assign a column from a transform; convenience wrapper for in-place column conversion |
| `MapToColumns` | Apply a row-wise mapping function over several columns; auto-detects which columns to pass from the mapped function's own argument names |
| `UseColumns` | Restrict a sub-pipeline to a column subset for performance, re-integrating the result |
| `SetField`, `Apply` | Set a field on a row Series; vectorised `Series.apply` wrapper |
| `SeriesWhere`, `DFWhere` | Conditionally apply a sub-pipeline to masked rows (see Core concepts) |
| `ConstructDataFrame`, `ConstructSeries` | Build a DataFrame/Series from arbitrary input data |

**Dtype / datetime transforms** (`etl_framework/operations/pandas/transforms/{conversions,numeric,timestamps}.py`)

| Operation | Purpose |
|---|---|
| `AsType`, `StringToInteger`, `ToList`, `ToArray` | Type conversion — `AsType` refuses `.astype(str)` unless `allow_str=True` is explicitly passed, since it silently turns `NaN` into the string `"nan"` |
| `ToNumeric`, `ToNullableInteger`, `Floor` | Numeric coercion, including pandas nullable-integer dtype |
| `ColumnToDatetime`, `ToTimedelta`, `TimestampFromColumns` | Parse/construct datetime and timedelta columns |
| `SetColumnTimezone`, `ConvertTimezone` | Localize/convert timezone on a datetime column |
| `DateTimeProperty`, `DatetimeToString`, `TimedeltaToSeconds` | Extract a datetime attribute; format/convert timedelta |

**String transforms** (`etl_framework/operations/pandas/transforms/string.py`)

| Operation | Purpose |
|---|---|
| `StringColumnSplit`, `StringColumnJoin` | Split a column into parts / join columns into one |
| `Replace`, `Strip`, `StringLength` | String cleanup |
| `ColumnRegexExtract`, `ColumnRegexFindall` | Regex extraction against a column |
| `BytesColumnToString` | Decode a bytes column to string |

**Validation** (`etl_framework/operations/pandas/validation.py`)

| Operation | Purpose |
|---|---|
| `Validate` | Assert a condition holds over the input, raising on failure |

## Extractors & writers

Extractors (`etl_framework/operations/pandas/record_extractors/`) turn raw input into a typed pandas DataFrame, driven by a per-field schema (each field declares its own name, source position/key, and dtype/converter):

- **`DelimitedRecordExtractor`** — the most commonly used extractor; wraps `pandas.read_csv` with per-field dtype injection via typed `Field` classes (`IntegerField`, `NumberField`, `TimestampField`, `StringField`, ...), as used in the quickstart above.
- **`BinaryFixedWidthRecordExtractor`** ("BFW") — byte-offset/length field records, used originally for legacy telecom switch output formats.
- **`ASN1BERRecordExtractor`** — a hand-written ASN.1 BER decoder for telecom CDR/billing-record formats, selecting fields by ASN.1 tag path. This is the most involved piece of the codebase's telecom heritage, and worth a look in `etl_framework/operations/pandas/record_extractors/asn1_ber/` if you're interested in binary protocol decoding. It also ships **experimental Cython- and Numba-accelerated decoder variants** (`asn1_decoder_cython.py`, `asn1_decoder_numba.py`, behind the `cython-experiments`/`numba-experiments` extras) as drop-in replacements for the pure-Python decoder — kept in the repo as a deliberate performance-engineering exploration rather than the default code path.
- **`RegexRecordExtractor`** and **`ASCIIPartitionedRecordExtractor`** — regex- and fixed-position-based extractors, marked as experimental/unfinished in their own docstrings.

Writers/exporters (`etl_framework/operations/io/writers.py`, `etl_framework/operations/pandas/output_generators/`) send a pipeline's output somewhere:

- **`LocalFileWriter`** — writes to the local filesystem atomically (writes to a `.tmp` path, then `os.rename`s into place), with optional gzip compression inferred from the output filename.
- **`HDFSFileSystemWriter`** — writes to HDFS (requires the `hdfs` extra).
- **`STDOUTWriter`** — writes to stdout (binary or text).
- **`DataFrameToCSVExporter`** — exports a DataFrame to CSV bytes/text for use with any of the above writers.

## Notes / gotchas

- **`pd.set_option('mode.chained_assignment', 'raise')` is set at import time.** Importing `etl_framework.operations.pandas.constructors` (which happens transitively via `etl_framework.operations.pandas`) sets this pandas option globally for the process, so any ambiguous chained-assignment elsewhere in your code will raise a `SettingWithCopyError` instead of the default warning. This is a deliberate defensive choice — the library relies on precise DataFrame copy semantics internally and would rather fail loudly than risk a silent incorrect write — but it *is* a global side effect of importing the package, worth knowing about if you use pandas elsewhere in the same process.
- **`AsType(to_type=str)` raises by default.** Pass `allow_str=True` if you really want `.astype(str)`; otherwise you'll get an `OperationConfigurationError` explaining why (it silently turns `NaN` into the string `"nan"`).
- **`DFWhere` will raise `InvalidOperationError`** if you nest `DropRows`, `DropColumns`, `RenameColumns`, or `Explode` inside it — these operations change row/column structure in ways that break its masking strategy.
- **Errors raised deep in a pipeline are wrapped in `OperationError`**, which records the full nested-operation call stack (innermost first) so you can see exactly which operation, at which point in a long chain, failed — rather than a bare traceback into `pandas` internals.

## Testing

The test suite is standard-library `unittest`, under `etl_framework/tests/`. Run it with either:

```bash
python -m unittest discover -s etl_framework/tests
```

or, with the `dev` extra installed (`pip install -e ".[dev]"`), pytest can run the same tests:

```bash
pytest etl_framework/tests
```

## License

MIT — see [LICENSE](LICENSE).
