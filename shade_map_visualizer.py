import xml.etree.ElementTree as ET
import folium
from folium import plugins
from datetime import datetime
import os
import numpy as np
from geopy.distance import geodesic

def parse_gpx_file(file_path):
    tree = ET.parse(file_path)
    root = tree.getroot()
    namespace = {'gpx': 'http://www.topografix.com/GPX/1/0'}
    
    waypoints = []
    for wpt in root.findall('.//gpx:wpt', namespace):
        lat = float(wpt.get('lat'))
        lon = float(wpt.get('lon'))
        name = wpt.find('gpx:name', namespace)
        time = wpt.find('gpx:time', namespace)
        
        waypoint = {
            'lat': lat,
            'lon': lon,
            'type': name.text.lower() if name is not None else 'unknown',
            'time': datetime.strptime(time.text, "%Y-%m-%dT%H:%M:%S.%fZ") if time is not None else None
        }
        waypoints.append(waypoint)
    
    waypoints.sort(key=lambda x: x['time'])
    return waypoints

def calculate_shade_stats(segments):
    total_distance = 0
    shade_distance = 0
    total_time = datetime.timedelta()
    shade_time = datetime.timedelta()

    for start, end, type in segments:
        distance = geodesic((start['lat'], start['lon']), (end['lat'], end['lon'])).meters
        time = end['time'] - start['time']
        
        total_distance += distance
        total_time += time
        
        if type == 'shade':
            shade_distance += distance
            shade_time += time
    
    sun_time = total_time - shade_time
    
    if total_distance > 0:
        shade_percentage = (shade_distance / total_distance) * 100
    else:
        shade_percentage = 0

    return shade_percentage, shade_time, sun_time

def create_shade_map(all_waypoints):
    if not all_waypoints:
        print("No waypoints found.")
        return None

    # Calculate the center of the map
    lats = [wp['lat'] for walk in all_waypoints for wp in walk]
    lons = [wp['lon'] for walk in all_waypoints for wp in walk]
    center_lat, center_lon = np.mean(lats), np.mean(lons)
    
    # Create a dark mode map centered on the mean coordinate
    m = folium.Map(location=[center_lat, center_lon], zoom_start=15, tiles="cartodbdark_matter")

    # Define colors for sun and shade
    sun_color = '#FFD700'  # Gold
    shade_color = '#4169E1'  # Royal Blue

    # Define line thickness
    line_weight = 10

    # Add paths for each walk
    for walk in all_waypoints:
        segments = []
        current_type = None
        segment_start = None

        for wp in walk:
            if wp['type'] in ['sun', 'shade']:
                if current_type != wp['type']:
                    if segment_start is not None:
                        segments.append((segment_start, wp, current_type))
                    segment_start = wp
                    current_type = wp['type']

        # Add the last segment
        if segment_start is not None and walk[-1] != segment_start:
            segments.append((segment_start, walk[-1], current_type))

        # Calculate shade stats
        shade_percentage, shade_time, sun_time = calculate_shade_stats(segments)

        # Draw the segments
        for start, end, type in segments:
            color = sun_color if type == 'sun' else shade_color
            folium.PolyLine(
                locations=[(start['lat'], start['lon']), (end['lat'], end['lon'])],
                color=color,
                weight=line_weight,
                opacity=0.8
            ).add_to(m)

        # Add annotation
        if walk:
            start_time = walk[0]['time']
            end_time = walk[-1]['time']
            duration = end_time - start_time
            
            annotation = (f"Date: {start_time.strftime('%Y-%m-%d')}<br>"
                          f"Start Time: {start_time.strftime('%H:%M:%S')}<br>"
                          f"Duration: {duration}<br>"
                          f"Time in Sun: {sun_time}<br>"
                          f"Time in Shade: {shade_time}<br>"
                          f"Shade: {shade_percentage:.1f}%")
            folium.Marker(
                location=(walk[0]['lat'], walk[0]['lon']),
                popup=annotation,
                icon=folium.Icon(color='green', icon='info-sign')
            ).add_to(m)

    # Add a legend
    legend_html = '''
         <div style="position: fixed; 
                     bottom: 50px; left: 50px; width: 120px; height: 90px; 
                     border:2px solid grey; z-index:9999; font-size:14px;
                     background-color: rgba(255, 255, 255, 0.8);">
             <p><strong>Legend</strong></p>
             <p><i style="background: {}; width: 50px;">&nbsp;</i>&nbsp;Sun</p>
             <p><i style="background: {}; width: 50px;">&nbsp;</i>&nbsp;Shade</p>
         </div>
         '''.format(sun_color, shade_color)
    m.get_root().html.add_child(folium.Element(legend_html))

    # Add a fullscreen option
    plugins.Fullscreen().add_to(m)

    return m

def process_gpx_files(directory):
    all_walks = []
    for filename in os.listdir(directory):
        if filename.endswith('.gpx'):
            file_path = os.path.join(directory, filename)
            waypoints = parse_gpx_file(file_path)
            all_walks.append(waypoints)
    return all_walks

# Directory containing GPX files
gpx_directory = 'gpx'

# Process all GPX files in the directory
all_waypoints = process_gpx_files(gpx_directory)

# Create the shade map
shade_map = create_shade_map(all_waypoints)

if shade_map:
    # Save the map as index.html
    shade_map.save('index.html')
    print("Shade map has been generated and saved as 'index.html'")
else:
    print("Failed to generate map. Please check your GPX files.")