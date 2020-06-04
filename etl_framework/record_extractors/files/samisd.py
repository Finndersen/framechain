
# class SAMISDCiscoRecordExtractor(BaseRecordExtractor):
#     """
#     Record extractor for SAMISD CISCO
#     Each record group consists of a device details line (modem header) and multiple data flow volume detail lines
#     The in/out usage record lines are merged together by Flow ID (class name and Record Type) and then appended to Modem Header
#     """
#
#     def __call__(self, data_file):
#         record_cache = {}
#         for line_num, recordline in enumerate(data_file):
#             # Ignore file headers/trailers
#             if recordline[0] == '#':
#                 continue
#             # Split CSV line
#             csv_list = recordline.rstrip().split(',')
#             # Cisco Cable Modem record line
#             if csv_list[0] == '1':
#                 # The record cache is used to build records identified by flow_id with merged in/out usage volumes
#                 record_cache = {}
#                 modem_header = csv_list[1:]
#                 num_flows = int(csv_list[-1])
#             # Cisco Usage Record line
#             elif csv_list[0] == '2':
#                 # Get flow ID (class name and RecType)
#                 class_name = csv_list[6].rsplit('_', 1)[0].replace("'",
#                                                                    '')  # remove _'in' or '_out' part of Class name e.g. captive_in -> captive
#                 flow_id = class_name + csv_list[7]  # Record Type: 1 - Interim, 2- Stop
#                 direction = int(csv_list[
#                                     9])  # 1: downstream, 2: upstream. Determines whether to extract downstream or upstream data volume
#                 # Add new record component or merge with existing
#                 if flow_id in record_cache:
#                     # Update appropriate data volume field (upload or download)
#                     record_cache[flow_id][8 + direction] = csv_list[10]
#                 else:
#                     # Set Download Bytes (OctetsPassed field) and Upload Bytes (PktsPassed field)
#                     if direction == 1:
#                         csv_list[11] = '0'  # Set upload bytes to 0
#                     else:
#                         csv_list[11] = csv_list[10]  # Set upload bytes to OctetsPassed
#                         csv_list[10] = '0'  # Set Download bytes to 0
#                     # Set class name without _in or _out part
#                     csv_list[6] = class_name
#                     # Add new record component to record cache
#                     record_cache[flow_id] = csv_list[1:]
#                 num_flows -= 1
#                 # No more record components left in block, yield complete records
#                 if not num_flows:
#                     for rec in record_cache.values():
#                         yield line_num, modem_header + rec
#
#
# class SAMISDArrisRecordExtractor(BaseRecordExtractor):
#     """
#     Specialised Record extractor for SAMISD ARRIS
#     Similar to CISCO, records come in in/out pairs which can be merged for efficiency
#     """
#     def __call__(self, data_file):
#         # Prev_record stores details of the previous record component to be merged with the next
#         prev_record = {'id': None, 'data': None}
#         for line_num, recordline in enumerate(data_file):
#             # Split CSV line
#             csv_list = recordline.rstrip().split(',')
#             # Construct record ID from CM IP address,Class name and RecType
#             class_name = csv_list[26].rsplit('_', 1)[0].replace("'", '')
#             rec_id = ''.join((csv_list[13][6:], class_name, csv_list[19]))
#             direction = int(csv_list[27])
#             # Add new record component
#             if not rec_id == prev_record['id']:
#                 # Set Download Bytes (OctetsPassed field)
#                 if direction == 1:
#                     csv_list[29] = '0'  # Set upload bytes to 0
#                 else:
#                     csv_list[29] = csv_list[28]  # Set upload bytes to OctetsPassed
#                     csv_list[28] = '0'  # Set Download bytes to 0
#                 # Set class name without _in or _out part
#                 csv_list[26] = class_name
#                 # If there was previous incomplete record, save it to be processed
#                 if prev_record['id']:
#                     yield line_num, prev_record['data']
#                 # Add new record component
#                 prev_record['id'] = rec_id
#                 prev_record['data'] = csv_list
#             # Merge with previous existing record component
#             else:
#                 # Update appropriate data volume field (upload or download)
#                 prev_record['data'][27 + direction] = csv_list[28]
#                 # Reset previous record
#                 prev_record['id'] = None
#                 yield line_num, prev_record['data']
