"""
Operations which take some form of input (file data, list of dictionaries, etc) and produce a Dataframe of records
"""
from .asn1_ber import *
from .ascii_position import ASCIIPartitionedRecordExtractor
from .delimited import DelimitedRecordExtractor
