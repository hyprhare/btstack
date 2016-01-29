#!/usr/bin/env python
# BlueKitchen GmbH (c) 2014

import glob
import re
import sys
import os

import btstack_parser as parser

program_info = '''
BTstack Event Getter Generator for BTstack
Copyright 2016, BlueKitchen GmbH
'''

copyright = """/*
 * Copyright (C) 2016 BlueKitchen GmbH
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 *
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 * 3. Neither the name of the copyright holders nor the names of
 *    contributors may be used to endorse or promote products derived
 *    from this software without specific prior written permission.
 * 4. Any redistribution, use, or modification is done solely for
 *    personal benefit and not for any commercial purpose or for
 *    monetary gain.
 *
 * THIS SOFTWARE IS PROVIDED BY BLUEKITCHEN GMBH AND CONTRIBUTORS
 * ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 * FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL MATTHIAS
 * RINGWALD OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 * INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 * BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS
 * OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED
 * AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
 * OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF
 * THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
 * SUCH DAMAGE.
 *
 * Please inquire about commercial licensing options at 
 * contact@bluekitchen-gmbh.com
 *
 */
"""

hfile_header_begin = """

/*
 *  btstack_event.h
 *
 *  @brief BTstack event getter/setter
 *  @note  Don't edit - generated by tool/btstack_event_generator.py
 *
 */

#ifndef __BTSTACK_EVENT_H
#define __BTSTACK_EVENT_H

#if defined __cplusplus
extern "C" {
#endif

#include "btstack_util.h"
#include <stdint.h>

/* API_START */

"""

hfile_header_end = """

/* API_END */

#if defined __cplusplus
}
#endif

#endif // __BTSTACK_EVENT_H
"""

c_prototoype_simple_return = '''
/**
 * @brief {description}
 * @param Event packet
 * @return {result_name}
 * @note: btstack_type {format}
 */
static inline {result_type} {fn_name}(const uint8_t * event){{
    {code}
}}
'''

c_prototoype_struct_return = '''
/**
 * @brief {description}
 * @param Event packet
 * @param Pointer to storage for {result_name}
 * @note: btstack_type {format}
 */
static inline void {fn_name}(const uint8_t * event, {result_type} {result_name}){{
    {code}    
}}
'''

c_prototoype_unsupported = '''
/**
 * @brief {description}
 * @param Event packet
 * @return {result_name}
 * @note: btstack_type {format}
 */
//  static inline {result_type} {fn_name}(const uint8_t * event){{
//      not implemented yet
//  }}
'''

# global variables/defines
gen_path = '../src/btstack_event.h'

defines = dict()
defines_used = set()

param_read = {
    '1' : 'return event[{offset}];',
    'J' : 'return event[{offset}];',
    '2' : 'return READ_BT_16(event, {offset});',
    'L' : 'return READ_BT_16(event, {offset});',
    '3' : 'return READ_BT_24(event, {offset});',
    '4' : 'return READ_BT_32(event, {offset});',
    'H' : 'return READ_BT_16(event, {offset});',
    'B' : 'swap48(&event[{offset}], {result_name});',
    'R' : 'return &event[{offset}];',
    'T' : 'return (const char *) &event[{offset}];',
    'V' : 'return &event[{offset}];',
}

def c_type_for_btstack_type(type):
    param_types = { '1' : 'uint8_t', '2' : 'uint16_t', '3' : 'uint32_t', '4' : 'uint32_t', 'H' : 'hci_con_handle_t', 'B' : 'bd_addr_t',
                    'D' : 'const uint8_t *', 'E' : 'const uint8_t * ', 'N' : 'String' , 'P' : 'const uint8_t *', 'A' : 'const uint8_t *',
                    'R' : 'const uint8_t *', 'S' : 'const uint8_t *',
                    'J' : 'int', 'L' : 'int', 'V' : 'const uint8_t *', 'U' : 'BT_UUID',
                    'X' : 'GATTService', 'Y' : 'GATTCharacteristic', 'Z' : 'GATTCharacteristicDescriptor',
                    'T' : 'const char *'}
    return param_types[type]

def size_for_type(type):
    param_sizes = { '1' : 1, '2' : 2, '3' : 3, '4' : 4, 'H' : 2, 'B' : 6, 'D' : 8, 'E' : 240, 'N' : 248, 'P' : 16,
                    'A' : 31, 'S' : -1, 'V': -1, 'J' : 1, 'L' : 2, 'U' : 16, 'X' : 20, 'Y' : 24, 'Z' : 18, 'T':-1}
    return param_sizes[type]

def format_function_name(event_name):
    event_name = event_name.lower()
    if 'event' in event_name:
        return event_name;
    return event_name+'_event'

def template_for_type(field_type):
    global c_prototoype_simple_return
    global c_prototoype_struct_return
    types_with_struct_return = "B"
    if field_type in types_with_struct_return:
        return c_prototoype_struct_return
    else:
        return c_prototoype_simple_return

def all_fields_supported(format):
    global param_read
    for f in format:
        if not f in param_read:
            return False
    return True

def create_getter(event_name, field_name, field_type, offset, supported):
    global c_prototoype_unsupported
    global param_read

    description = "Get field %s from event %s" % (field_name, event_name)
    result_name = field_name
    fn_name     = "%s_get_%s" % (event_name, field_name)
    result_type = c_type_for_btstack_type(field_type)
    template = c_prototoype_unsupported
    code = ''
    if supported and field_type in param_read:
        template = template_for_type(field_type)
        code = param_read[field_type].format(offset=offset, result_name=result_name)
    return template.format(description=description, fn_name=fn_name, result_name=result_name, result_type=result_type, code=code, format=field_type)

def create_events(events):
    global gen_path
    global copyright
    global hfile_header_begin
    global hfile_header_end

    with open(gen_path, 'wt') as fout:
        fout.write(copyright)
        fout.write(hfile_header_begin)
        for event_type, event_name, format, args in events:
            if not event_name in [
                'SDP_QUERY_COMPLETE',
                'SDP_QUERY_RFCOMM_SERVICE',
                'SDP_QUERY_ATTRIBUTE_BYTE',
                'SDP_QUERY_SERVICE_RECORD_HANDLE']:
                continue                
            event_name = format_function_name(event_name)
            length_name = ''
            offset = 2
            supported = all_fields_supported(format)
            for f, arg in zip(format, args):
                field_name = arg
                field_type = f 
                text = create_getter(event_name, field_name, field_type, offset, supported)
                fout.write(text)
                if field_type in 'RT':
                    break
                offset += size_for_type(field_type)

        fout.write(hfile_header_end)

# set root
parser.set_btstack_root('..')

print(program_info)

# parse events
(events, le_events, event_types) = parser.parse_events()

# create event field accesors
create_events(events + le_events)

# done
print('Done!')
