# framechain

A library for declaratively building data-transformation pipelines on top of pandas. Pipelines are assembled from small, configurable `Operation` classes with simple interfaces — declare what each step should do, and the library handles doing it correctly and efficiently in pandas underneath: dtype coercion, copy semantics, conditional/masked application, column-scoped operations, and the other easy-to-get-wrong parts of the pandas API.

> Personal project, built while working at a telco data platform (~2021–2022). Not published to PyPI, not actively maintained — published here as a portfolio piece, not a supported package.

A pipeline is built from three kinds of component, each just an `Operation`: **extractors** parse raw input (CSV, fixed-width binary records, ASN.1-encoded records, …) into a pandas DataFrame; **operations** filter, join, and transform that data — including applying a transform to only specific columns or only rows matching a condition, without copying the whole DataFrame to do it; and **writers** send the result somewhere. Chaining all three together with `>>` produces one runnable pipeline object, which also gets execution profiling and Graphviz-based visualization for free.

## Philosophy

This library is built entirely on Python's operator overloading: a pipeline is a single composed `Operation` object. The base class, `Operation` (`framechain/operations/base.py`), overloads:

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

Composed into a full pipeline, that same style looks like this — an extractor parses a CSV into a DataFrame, a couple of transforms clean it up and derive a new column, and a writer exports the result, all chained with `>>` into one callable:

```python
record_extractor = DelimitedRecordExtractor(fields=[
    IntegerField('vendor_id', column_id='VendorID', size=8),
    TimestampField('pickup_timestamp', column_id='tpep_pickup_datetime'),
    TimestampField('dropoff_timestamp', column_id='tpep_dropoff_datetime'),
])

pipeline = (
    LocalFileReader() >> record_extractor
    >> DropRows(Column('vendor_id') >> IsNull())
    >> SetColumn('trip_duration', (Column('dropoff_timestamp') - Column('pickup_timestamp')) >> TimedeltaToSeconds())
    >> DataFrameToCSVExporter() >> LocalFileWriter('output/trips.csv')
)

pipeline('data/yellow_tripdata_2021-01.csv')
```

(imports omitted for brevity — the [Quickstart](#quickstart) below builds this same pipeline up in full, one component at a time, with imports, profiling, and visualization)

...while remaining **lazy, composable and introspectable** rather than eagerly evaluated. Every operator call just builds a small tree of `Operation` objects; nothing runs until the resulting object is called with an input. A raw Python value or plain function dropped into that expression is auto-wrapped as a `Value` or `Lambda` operation by `convert_to_operation()`, so scalars and callables compose transparently alongside `Operation` instances.

Because every node in a pipeline is a plain, introspectable Python object, the library gets several capabilities essentially for free — most notably built-in profiling and visualization (see [Quickstart](#quickstart) and [Core concepts](#core-concepts) below) that apply uniformly to *any* pipeline, however it's composed, without additional instrumentation.

## Installation

Not published to PyPI. Install from a clone in editable mode:

```bash
git clone <repo-url>
cd framechain
pip install -e ".[dev]"
```

Optional extras (from `pyproject.toml`), combine as needed, e.g. `pip install -e ".[dev,viz]"`:

| Extra | Adds | Unlocks |
|---|---|---|
| `dev` | `pytest` | Running the test suite |
| `viz` | `pydot`, `snakeviz` | `show_graph()` pipeline visualization and `profile_snakeviz()` profiling UI |
| `crypto` | `pycryptodome` | AES encrypt/decrypt operations (`framechain/operations/cryptography.py`) |
| `hdfs` | `hdfs` | `HDFSFileSystemWriter` |
| `cython-experiments` | `Cython` | The experimental Cython-accelerated ASN.1 BER decoder |
| `numba-experiments` | `numba` | The experimental Numba-accelerated ASN.1 BER decoder |

Core runtime dependencies are just `pandas`, `numpy`, `pytz`, and `python-dateutil`. Requires Python 3.8+.

## Quickstart

This builds a pipeline over the public [NYC TLC Yellow Taxi trip data](https://www1.nyc.gov/site/tlc/about/tlc-trip-record-data.page), one component at a time — an extractor, some operations, and a writer — then chains them together. See `Demo.ipynb` for the same pipeline as a runnable notebook.

### Extractors

An extractor parses raw input into a typed pandas DataFrame. Each field declares its own name, source column, and dtype, so there's no separate `read_csv()` + manual coercion step:

```python
from framechain.operations.io import LocalFileReader
from framechain.operations.pandas.record_extractors.delimited import (
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

### Operations

Operations filter, clean, and transform the DataFrame — composed the same way as any other `Operation`, using the overloaded operators from [Philosophy](#philosophy) above. This drops invalid rows, derives a trip-duration column, applies a 10% surcharge only to card payments without touching any other rows, and computes a derived rate:

```python
from framechain.operations.pandas import DropRows, Column, IsNull, TimedeltaToSeconds, SetColumn, DFWhere

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

`add_card_surcharge` deliberately uses `DFWhere` rather than a plain `df.loc[mask, 'fare_amount'] *= 1.1` — see [Core concepts](#core-concepts) for why that matters beyond style.

### Output generators

Output generators/writers send the result somewhere. Exporting a DataFrame to a format (CSV, here) and writing the result out are separate, composable steps:

```python
from framechain.operations.pandas import DataFrameToCSVExporter
from framechain.operations.io import LocalFileWriter

write_output = DataFrameToCSVExporter() >> LocalFileWriter('output/trips_transformed.csv')
```

### Putting it together

Each of the three components above is just an `Operation`, so they chain together the same way as anything else, into one pipeline running from a raw file path to a written output file:

```python
full_pipeline = read_extract_records >> transforms >> write_output
full_pipeline('data/yellow_tripdata_2021-01.csv')
```

The same pipeline object also gives you profiling and visualization for free, with no extra setup:

```python
full_pipeline.profile_snakeviz('data/yellow_tripdata_2021-01.csv')  # opens a SnakeViz flame graph in Jupyter
full_pipeline.show_graph()  # renders the pipeline structure as a Graphviz diagram
```

![Graph of the pipeline built above, generated by show_graph()](docs/pipeline_graph.svg)

*The actual output of `show_graph()` for the pipeline built above.*

## Core concepts

**Operator-based chaining.** `>>` is the pipeline backbone: `a >> b >> c` builds a single `ChainedOperations` (flattening automatically, so chaining a chain doesn't nest), which calls each stage in order, passing output to input. Any pipeline is itself just an `Operation`, so it can be embedded inside a larger one.

**`Column` / `SetColumn`.** `Column('x')` is an `Operation` that extracts column `'x'` from whatever DataFrame or Series it's called with; it participates in arithmetic and comparisons like any other operation. `SetColumn('y', <transform>)` runs `<transform>` against the input DataFrame and assigns the resulting Series onto (new or existing) column `'y'`, returning a new DataFrame with a shallow copy semantics.

**`DFWhere` / `SeriesWhere` and `get_required_columns()`.** These conditionally apply a wrapped operation to only the rows matching a boolean mask, then integrate the result back into the original data. `DFWhere` (the DataFrame version) is genuinely optimized, not just a convenience wrapper: `DataframeOperation` subclasses (`Column`, `SetColumn`, `DropColumns`, `Merge`, etc., in `framechain/operations/pandas/base.py`) each implement `get_required_columns()`, and `DFWhere` walks the operation tree it wraps (via `Operation.search()`) to automatically infer exactly which columns the wrapped transform needs and which it changes. It then slices the DataFrame down to only those columns before masking and copying, instead of copying the whole frame — a meaningful performance/memory win on wide DataFrames, derived directly from the pipeline's own structure rather than hand-tuned. `DFWhere` explicitly refuses to wrap `DropRows`, `DropColumns`, `RenameColumns`, or `Explode` (raising `InvalidOperationError`), since row/column-dropping operations inside it would break the masking/reintegration strategy.

**Extractor → transforms → writer.** The idiomatic shape of a full pipeline is `Extractor >> transform_operations >> Writer`, as built up in [Quickstart](#quickstart) above.

**Built-in observability.** Every `Operation` carries its own execution profiling — `enable_profiling()` / `disable_profiling()` toggle a custom cProfile-like recorder that tracks call counts and cumulative/self time *per operation instance*, correctly attributing time to whichever specific parent invoked a shared child operation (something a standard flat profiler can't do, since it only tracks time per function, not per position in a call graph). `profile_snakeviz(input)` runs the pipeline under this profiler and opens the result in [SnakeViz](https://jiffyclub.github.io/snakeviz/) inside a Jupyter notebook, using pstats-compatible output. Separately, `show_graph()` renders the pipeline's structure as a Graphviz diagram (via `pydot`), useful for seeing the shape of a deeply chained or forked pipeline at a glance. Both require the `viz` extra.

## Operation catalogue

Grouped by module, not exhaustive — see docstrings in source for full parameter details.

**Core / generic** (`framechain/operations/{general,control,logical,conditional,wrappers}.py`)

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

**Pandas column/value operations** (`framechain/operations/pandas/{general,conditional}.py`)

| Operation | Purpose |
|---|---|
| `Column` | Select a column from a DataFrame or a field from a row Series |
| `MapColumnValues`, `ColumnOfValue`, `FillNA` | Value mapping, constant column, NA filling |
| `Min` / `Max` | Row-wise or column-wise min/max |
| `Copy`, `PrintDF` | Defensive copy; debug-print a DataFrame |
| `IsIn`, `IsNull`, `IsEmpty`, `StringContains`, `StartsWith`, `IsNumeric`, `FieldExists` | Boolean-mask-producing column conditions |
| `MergeRowValues` | Combine several row fields with a custom merge/filter function |

**DataFrame-level operations** (`framechain/operations/pandas/dataframe.py`)

| Operation | Purpose |
|---|---|
| `DropRows`, `DropColumns`, `RenameColumns`, `Sort` | Standard row/column manipulation |
| `MultipleFillNA`, `Explode` | Bulk NA fill; explode list-like column into rows |
| `Combine`, `CombineFirst` | Elementwise / first-non-null combination of two columns |
| `SelectColumns`, `AlignCategories` | Column projection/ordering; align categorical dtypes |
| `Merge` | Join two DataFrames — validates that join-column dtypes actually match before merging, raising a clear `TypeError` instead of a confusing downstream failure |
| `CreateDuplicateRows` | Duplicate rows matching a condition |

**Pipeline-construction operations** (`framechain/operations/pandas/constructors.py`)

| Operation | Purpose |
|---|---|
| `SetColumn`, `ConvertColumn` | Assign a column from a transform; convenience wrapper for in-place column conversion |
| `MapToColumns` | Apply a row-wise mapping function over several columns; auto-detects which columns to pass from the mapped function's own argument names |
| `UseColumns` | Restrict a sub-pipeline to a column subset for performance, re-integrating the result |
| `SetField`, `Apply` | Set a field on a row Series; vectorised `Series.apply` wrapper |
| `SeriesWhere`, `DFWhere` | Conditionally apply a sub-pipeline to masked rows (see Core concepts) |
| `ConstructDataFrame`, `ConstructSeries` | Build a DataFrame/Series from arbitrary input data |

**Dtype / datetime transforms** (`framechain/operations/pandas/transforms/{conversions,numeric,timestamps}.py`)

| Operation | Purpose |
|---|---|
| `AsType`, `StringToInteger`, `ToList`, `ToArray` | Type conversion — `AsType` refuses `.astype(str)` unless `allow_str=True` is explicitly passed, since it silently turns `NaN` into the string `"nan"` |
| `ToNumeric`, `ToNullableInteger`, `Floor` | Numeric coercion, including pandas nullable-integer dtype |
| `ColumnToDatetime`, `ToTimedelta`, `TimestampFromColumns` | Parse/construct datetime and timedelta columns |
| `SetColumnTimezone`, `ConvertTimezone` | Localize/convert timezone on a datetime column |
| `DateTimeProperty`, `DatetimeToString`, `TimedeltaToSeconds` | Extract a datetime attribute; format/convert timedelta |

**String transforms** (`framechain/operations/pandas/transforms/string.py`)

| Operation | Purpose |
|---|---|
| `StringColumnSplit`, `StringColumnJoin` | Split a column into parts / join columns into one |
| `Replace`, `Strip`, `StringLength` | String cleanup |
| `ColumnRegexExtract`, `ColumnRegexFindall` | Regex extraction against a column |
| `BytesColumnToString` | Decode a bytes column to string |

**Validation** (`framechain/operations/pandas/validation.py`)

| Operation | Purpose |
|---|---|
| `Validate` | Assert a condition holds over the input, raising on failure |

## Extractors & writers

Extractors (`framechain/operations/pandas/record_extractors/`) turn raw input into a typed pandas DataFrame, driven by a per-field schema (each field declares its own name, source position/key, and dtype/converter):

- **`DelimitedRecordExtractor`** — the most commonly used extractor; wraps `pandas.read_csv` with per-field dtype injection via typed `Field` classes (`IntegerField`, `NumberField`, `TimestampField`, `StringField`, ...), as used in the quickstart above.
- **`BinaryFixedWidthRecordExtractor`** ("BFW") — byte-offset/length field records, used originally for legacy telecom switch output formats.
- **`ASN1BERRecordExtractor`** — a hand-written ASN.1 BER decoder for telecom CDR/billing-record formats, selecting fields by ASN.1 tag path. This is the most involved piece of the codebase's telecom heritage, and worth a look in `framechain/operations/pandas/record_extractors/asn1_ber/` if you're interested in binary protocol decoding. It also ships **experimental Cython- and Numba-accelerated decoder variants** (`asn1_decoder_cython.py`, `asn1_decoder_numba.py`, behind the `cython-experiments`/`numba-experiments` extras) as drop-in replacements for the pure-Python decoder — kept in the repo as a deliberate performance-engineering exploration rather than the default code path.
- **`RegexRecordExtractor`** and **`ASCIIPartitionedRecordExtractor`** — regex- and fixed-position-based extractors, marked as experimental/unfinished in their own docstrings.

Writers/exporters (`framechain/operations/io/writers.py`, `framechain/operations/pandas/output_generators/`) send a pipeline's output somewhere:

- **`LocalFileWriter`** — writes to the local filesystem atomically (writes to a `.tmp` path, then `os.rename`s into place), with optional gzip compression inferred from the output filename.
- **`HDFSFileSystemWriter`** — writes to HDFS (requires the `hdfs` extra).
- **`STDOUTWriter`** — writes to stdout (binary or text).
- **`DataFrameToCSVExporter`** — exports a DataFrame to CSV bytes/text for use with any of the above writers.

## Notes / gotchas

- **`pd.set_option('mode.chained_assignment', 'raise')` is set at import time.** Importing `framechain.operations.pandas.constructors` (which happens transitively via `framechain.operations.pandas`) sets this pandas option globally for the process, so any ambiguous chained-assignment elsewhere in your code will raise a `SettingWithCopyError` instead of the default warning. This is a deliberate defensive choice — the library relies on precise DataFrame copy semantics internally and would rather fail loudly than risk a silent incorrect write — but it *is* a global side effect of importing the package, worth knowing about if you use pandas elsewhere in the same process.
- **`AsType(to_type=str)` raises by default.** Pass `allow_str=True` if you really want `.astype(str)`; otherwise you'll get an `OperationConfigurationError` explaining why (it silently turns `NaN` into the string `"nan"`).
- **`DFWhere` will raise `InvalidOperationError`** if you nest `DropRows`, `DropColumns`, `RenameColumns`, or `Explode` inside it — these operations change row/column structure in ways that break its masking strategy.
- **Errors raised deep in a pipeline are wrapped in `OperationError`**, which records the full nested-operation call stack (innermost first) so you can see exactly which operation, at which point in a long chain, failed — rather than a bare traceback into `pandas` internals.

## Testing

The test suite is standard-library `unittest`, under `framechain/tests/`. Run it with either:

```bash
python -m unittest discover -s framechain/tests
```

or, with the `dev` extra installed (`pip install -e ".[dev]"`), pytest can run the same tests:

```bash
pytest framechain/tests
```

## License

MIT — see [LICENSE](LICENSE).
