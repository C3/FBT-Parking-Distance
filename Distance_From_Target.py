# Check readme for requirements and API dependencies

print('Importing libraries', end='', flush=True)
from googlemaps import Client
import pandas as pd
import os
import time
import sys
import math
print(' - done.')



print('Setting parameters', end='', flush=True)
# config variables
api_key='<your key>'
folder = '<folder>'
file = '<filename>'
target_coords = '-31.9462624,115.8392199' # THe coords of your target destination; currently not used
target_address = '705/707 Murray Street, West Perth WA' # Address of your target destination; used for route distance
api_throttle_threshold = 10 # Wait after this many API calls to avoid quota restriction. -1 = no restriction.
api_throttle_wait_time = 10 # HOw many seconds to wait for when threshold met
chunk_size = 5 # How many records are processed before they are written to file
start_at_index = 665 # If something failed, set this index of the next record to be processed
input_file = os.path.join(folder,file)
output_file = os.path.join(folder,'results.csv')
print(' - done.')


print('Initialising googlemaps API', end='', flush=True)
# initialise the google maps client
gmaps = Client(key=api_key)
print(' - done.')



def geocode_address(address):
    """Return a 3 tuple containing the Formatted address (string),
    Latitude (float) and Longitude (float)."""
    # Use Google to geocode
    geocode_result = gmaps.geocode(address)
    # Return the prepared tuple
    return (geocode_result[0]['formatted_address'], \
        geocode_result[0]['geometry']['location']['lat'], \
        geocode_result[0]['geometry']['location']['lng']
        )

def get_route(start_address, end_address):
    """
    Return a Directions object representing the directions from
    start_address to end_address.
    """
    return gmaps.directions(origin=start_address, destination=end_address)

def get_route_distance(route, units):
    """
    Return the distance in metres or kilometres for the route.

    Parameters:
    route: a route object provided by get_route()
    units: the desired distance units ('meters' or 'kilometers'), not the US spelling.
    """
    # validate the provided units and fail if not recognised.
    return_units = ''
    if units == 'meters' or units == 'kilometers':
        return_units = units
    else:
        raise ValueError('The provided units are not supported. Please use either "meters" or "kilometers".')
    # route will be [] if no route could be found
    try:
        distance = route[0]['legs'][0]['distance']['value']
        return distance
    except IndexError:
        # google couldn't find a route and returned []
        return None

def distance_to_target_from_address(address):
    """
    Return the distance in meters from address to target.
    """
    route = gmaps.directions(origin=address, destination=target_address, mode='walking', units='meters')
    return get_route_distance(route, 'meters')

def distance_to_target_from_location(location):
    """
    Return the distance in meters from address to target.
    """
    route = gmaps.directions(origin=location, destination=target_coords, mode='walking', units='meters')
    return get_route_distance(route, 'meters')

def make_searchable_address(name='', address='', is_street_address=''):
    result = ''
    if is_street_address == 'no':
        # without a street address, use the business name and approximate suburb
        result = name.lower() + ', subiaco, wa australia'
    else:
        # use the street address if we have it
        result = cleanse_address(address)
    return result

def cleanse_address(string):
    # split address lines have had the LF (\n) replaced with a |
    # remove the first section if it does not start with a numeric
    return string.lower()
#     segments = string.lower().split('|')
#     if len(segments) <= 1:
#         # there are no splits, so just return it
#         return string.lower()
#     else:
#         # more than one segment
#         if segments[0][0].isnumeric():
#             # looks like a street address, rebuild and return
#             return ', '.join(segments)
#         else:
#             # has a junk 1st segment: level, unit, building name or something
#             return ', '.join(segments[1:])

def prepare_addresses(df):
    for i in df.index:
        # start by testing if this is a street or PO Box address
        if 'po box' in df.loc[i]['Mailing_Address'].lower() or 'p.o box' in df.loc[i]['Mailing_Address'].lower() or 'p.o. box' in df.loc[i]['Mailing_Address'].lower():
            df.set_value(i, 'is_street_address', 'no')
        else:
            df.set_value(i, 'is_street_address', 'yes')
        # based on the address type, form the address search string
        df.set_value(i, 'address_to_search', make_searchable_address(df.loc[i]['Company_Name'], df.loc[i]['Mailing_Address'], df.loc[i]['is_street_address']))
        # check the address search string again, incase it is still malformed
#         if not df.loc[i]['Mailing_Address'][0].isnumeric(): # if 1st char of address is not a number
#             df.set_value(i, 'is_street_address', 'no')
        
def perform_distance_calcs(df):
    for i in df.index:
        print('    Starting record ', i)
        # see if google can find the address
        print('        Looking for: ', df.loc[i]['address_to_search'])
        place = gmaps.places(df.loc[i]['address_to_search'])
        print('        Status: ', place['status'])
        if place == None or place == []:
            # Something horrible happened
            df.set_value(i, 'status', 'Place resolution failed: blank result')
        
        elif place['status'] != 'OK': 
            # gmaps couldn't find it, give up for all hope is lost
            print('        Couldnt find it.')
            df.set_value(i, 'status', 'Place resolution failed: status = ', place['status'])

        else: # we found it, so populate the relevant columns
            # place has been resolved
            if len(place['results']) > 1:
                # Found more than one address. Use results[0], but warn the user.
                df.set_value(i, 'status', 'Place resolved but ambiguous: results = ', len(place['results']))
            else:
                # Found just one address. Good.
                df.set_value(i, 'status', 'Place resolved and unambiguous')
            try:
                print('        Found ', len(place['results']), ' results:')
                print('        Best: ', place['results'][0]['name'], ' @ ', place['results'][0]['formatted_address'])
                if len(place['results']) > 1:
                    for j in range(1,len(place['results'])):
                        print('        Other: ', place['results'][j]['name'], ' @ ', place['results'][j]['formatted_address'])
                df.set_value(i, 'googlemaps_business_name', place['results'][0]['name'])
                df.set_value(i, 'googlemaps_address', place['results'][0]['formatted_address'])
                df.set_value(i, 'googlemaps_location', str(place['results'][0]['geometry']['location']['lat']) + ',' +  str(place['results'][0]['geometry']['location']['lng']))
                df.set_value(i, 'meters_to_target', distance_to_target_from_address(df.loc[i]['googlemaps_address']))
                print('        Distance to target: ', df.loc[i]['meters_to_target'])
            except IndexError:
                print('        IndexError: The place is missing a requested attribute')
                df.set_value(i, 'status', 'Place missing requested attribute')
                continue
            except UnicodeEncodeError:
                print('        UnicodeEncodeError: The place has a mangled name')
                df.set_value(i, 'status', 'UnicodeEndoceError')
                continue
        # Throttle calls through the API
        print('\n')
        if api_throttle_threshold != -1:
            if i % api_throttle_threshold == 0 and i > 0: 
                print('\nGiving the API a rest for ', api_throttle_wait_time, ' secs ',end="",flush=True)
                for i in range(0, api_throttle_wait_time):
                    time.sleep(1) # pause for n secs every five addresses to avoid exceeding api query limits
                    print('.',end="",flush=True)
                print()

            
print('Reading the input file', end='', flush=True)
df = pd.read_csv(input_file, encoding='utf-8', engine='python')
print(' - done.')

print('Preparing the data structure', end='', flush=True)
# check for a starting index
if start_at_index != 0:
    # use a slice of the dataframe from start_at_index to the end
    df = df.loc[start_at_index:]
# get the columns that we'll need
df['is_street_address'] = ''
df['address_to_search'] = ''
df['status'] = ''
df['googlemaps_business_name'] = ''
df['googlemaps_address'] = ''
df['googlemaps_location'] = ''
df['measure_to_address'] = target_address
df['meters_to_target'] = ''
print(' - done.')

# process the set in chunks of 'chunk_size' to minimise disruption from connection issues
# or quota errors
num_chunks = math.ceil(len(df.index) / chunk_size)

# loop through each chunk and write to file
for iteration in range(0, num_chunks):
    # calculate the bounds of this chunk
    start_i = iteration*chunk_size
    end_i = min((iteration+1)*chunk_size, max(df.index))
    # take a slice of the whole dataframe
    chunk = df.iloc[start_i : end_i]
    print('Starting chunk ', iteration, ', records: ', start_i, '-', end_i, ' of ', max(df.index))
    
    print('Chunk: ', iteration, ': Formatting the addresses')
    prepare_addresses(chunk)
    print('Addresses formatted.')

    print('Chunk: ', iteration, ': Resolving the addresses and calculating the route distances')
    perform_distance_calcs(chunk)
    print('Addresses resolved.')

    print('Chunk: ', iteration, ': Calculations complete. Writing results to ', output_file, end='', flush=True)
    open_mode = ''
    if iteration == 0 and start_at_index == 0:
        open_mode = 'w' # overwrite the first time
    else:
        open_mode = 'a' # append every other time, or if resuming

    with open(output_file, open_mode) as f:
        chunk.to_csv(f)
    print(' - done.')
    
    print('Chunk: ', iteration, ': Complete.')
    
print('All chunks complete.')
