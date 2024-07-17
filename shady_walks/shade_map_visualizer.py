import xml.etree.ElementTree as ET
import folium
from folium import plugins
from datetime import datetime, timedelta  # Add timedelta to the import
import os
import numpy as np
from geopy.distance import geodesic

import pytz

def format_duration(duration):
    hours, remainder = divmod(int(duration.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m {seconds}s"

def filter_erroneous_points(trackpoints, max_speed_kmh=30):
    filtered_points = []
    for i, point in enumerate(trackpoints):
        if i == 0:
            filtered_points.append(point)
            continue
        
        prev_point = filtered_points[-1]
        time_diff = (point['time'] - prev_point['time']).total_seconds()
        if time_diff == 0:
            continue  # Skip points with the same timestamp
        
        distance = geodesic((prev_point['lat'], prev_point['lon']), (point['lat'], point['lon'])).km
        speed_kmh = (distance / time_diff) * 3600
        
        if speed_kmh <= max_speed_kmh:
            filtered_points.append(point)
    
    return filtered_points

def parse_gpx_file(file_path):
    tree = ET.parse(file_path)
    root = tree.getroot()
    namespace = {'gpx': 'http://www.topografix.com/GPX/1/0'}
    
    waypoints = []
    trackpoints = []

    eastern = pytz.timezone('US/Eastern')
    
    # Parse waypoints
    for wpt in root.findall('.//gpx:wpt', namespace):
        lat = float(wpt.get('lat'))
        lon = float(wpt.get('lon'))
        name = wpt.find('gpx:name', namespace)
        time = wpt.find('gpx:time', namespace)
        
        if name is not None and name.text.lower() in ['sun', 'shade']:
            waypoint = {
                'lat': lat,
                'lon': lon,
                'type': name.text.lower(),
                'time': datetime.strptime(time.text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.UTC).astimezone(eastern) if time is not None else None
            }
            waypoints.append(waypoint)
    
    # Parse track points
    for trkpt in root.findall('.//gpx:trkpt', namespace):
        lat = float(trkpt.get('lat'))
        lon = float(trkpt.get('lon'))
        time = trkpt.find('gpx:time', namespace)
        
        trackpoint = {
            'lat': lat,
            'lon': lon,
            'time': datetime.strptime(time.text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.UTC).astimezone(eastern) if time is not None else None
        }
        trackpoints.append(trackpoint)
    
    # Sort waypoints and trackpoints by time
    waypoints.sort(key=lambda x: x['time'])
    trackpoints.sort(key=lambda x: x['time'])
    
    # Remove first 3 and last 3 data points
    if len(trackpoints) > 10:
        trackpoints = trackpoints[5:-5]
    
    # Filter out erroneous trackpoints
    trackpoints = filter_erroneous_points(trackpoints)
    
    # Assign sun/shade type to trackpoints based on waypoints
    current_type = 'unknown'
    waypoint_index = 0
    for trackpoint in trackpoints:
        while waypoint_index < len(waypoints) and waypoints[waypoint_index]['time'] <= trackpoint['time']:
            current_type = waypoints[waypoint_index]['type']
            waypoint_index += 1
        trackpoint['type'] = current_type
    
    return trackpoints

def calculate_shade_stats(segments):
    total_distance = 0
    shade_distance = 0
    total_time = timedelta()
    shade_time = timedelta()

    start_time = segments[0][0]['time']
    end_time = segments[-1][1]['time']
    total_time = end_time - start_time

    for start, end, type in segments:
        distance = geodesic((start['lat'], start['lon']), (end['lat'], end['lon'])).meters
        segment_time = end['time'] - start['time']
        
        total_distance += distance
        
        if type == 'shade':
            shade_distance += distance
            shade_time += segment_time
    
    sun_distance = total_distance - shade_distance
    sun_time = total_time - shade_time
    
    if total_distance > 0:
        shade_percentage = (shade_distance / total_distance) * 100
    else:
        shade_percentage = 0

    return shade_percentage, shade_distance, sun_distance, shade_time, sun_time, total_time




def create_shade_map(all_trackpoints):
    if not all_trackpoints:
        print("No trackpoints found.")
        return None

    # Calculate the center of the map
    lats = [tp['lat'] for walk in all_trackpoints for tp in walk]
    lons = [tp['lon'] for walk in all_trackpoints for tp in walk]
    center_lat, center_lon = np.mean(lats), np.mean(lons)
    
    # Create a dark mode map centered on the mean coordinate
    m = folium.Map(location=[center_lat, center_lon], zoom_start=15, tiles="cartodbdark_matter")
    
    # Add favicon links to the HTML head, pointing to the images subfolder
    favicon_html = '''
    <link rel="apple-touch-icon" sizes="180x180" href="images/apple-touch-icon.png">
    <link rel="icon" type="image/png" sizes="32x32" href="images/favicon-32x32.png">
    <link rel="icon" type="image/png" sizes="16x16" href="images/favicon-16x16.png">
    <link rel="manifest" href="images/site.webmanifest">
    <link rel="mask-icon" href="images/safari-pinned-tab.svg" color="#5bbad5">
    <meta name="msapplication-TileColor" content="#da532c">
    <meta name="theme-color" content="#ffffff">
    '''
    m.get_root().header.add_child(folium.Element(favicon_html))

    # Define colors for sun and shade
    sun_color = '#FFD700'  # Gold
    shade_color = '#4169E1'  # Royal Blue

    # Define line thickness
    line_weight = 5

    for walk in all_trackpoints:
        segments = []
        current_type = None
        segment_start = None

        for tp in walk:
            if current_type != tp['type']:
                if segment_start is not None:
                    segments.append((segment_start, tp, current_type))
                segment_start = tp
                current_type = tp['type']

        # Add the last segment
        if segment_start is not None and walk[-1] != segment_start:
            segments.append((segment_start, walk[-1], current_type))

        
        # Draw the segments
        for start, end, type in segments:
            color = sun_color if type == 'sun' else shade_color
            points = [(tp['lat'], tp['lon']) for tp in walk if start['time'] <= tp['time'] <= end['time']]
            folium.PolyLine(
                locations=points,
                color=color,
                weight=line_weight,
                opacity=0.8
            ).add_to(m)

        # Calculate shade stats
        shade_percentage, shade_distance, sun_distance, shade_time, sun_time, total_time = calculate_shade_stats(segments)

        # Calculate time-based shade percentage
        time_shade_percentage = (shade_time.total_seconds() / total_time.total_seconds()) * 100 if total_time.total_seconds() > 0 else 0

        # Add annotation
        if walk:
            start_time = walk[0]['time']
            end_time = walk[-1]['time']
            total_distance = shade_distance + sun_distance
            
            # Convert to imperial units
            total_distance_mi = total_distance * 0.000621371
            sun_distance_mi = sun_distance * 0.000621371
            shade_distance_mi = shade_distance * 0.000621371
            
            annotation = f"""
            <div style="font-family: Arial, sans-serif; max-width: 300px;">
                <h3 style="color: #333; border-bottom: 2px solid #333; padding-bottom: 5px;">Walk Summary</h3>
                <p><strong>Date:</strong> {start_time.strftime('%B %d, %Y')}</p>
                <p><strong>Start Time:</strong> {start_time.strftime('%I:%M %p')} ET</p>
                <p><strong>Duration:</strong> {format_duration(total_time)}</p>
                <h4 style="color: #555; margin-top: 15px;">Distance Breakdown</h4>
                <ul style="list-style-type: none; padding-left: 0;">
                    <li><strong>Total:</strong> {total_distance:.1f} m ({total_distance_mi:.2f} mi)</li>
                    <li style="color: #FFD700;"><strong>In Sun:</strong> {sun_distance:.1f} m ({sun_distance_mi:.2f} mi)</li>
                    <li style="color: #4169E1;"><strong>In Shade:</strong> {shade_distance:.1f} m ({shade_distance_mi:.2f} mi)</li>
                </ul>
                <h4 style="color: #555; margin-top: 15px;">Time Breakdown</h4>
                <ul style="list-style-type: none; padding-left: 0;">
                    <li><strong>Total:</strong> {format_duration(total_time)}</li>
                    <li style="color: #FFD700;"><strong>In Sun:</strong> {format_duration(sun_time)}</li>
                    <li style="color: #4169E1;"><strong>In Shade:</strong> {format_duration(shade_time)}</li>
                </ul>
                <h4 style="color: #555; margin-top: 15px;">Shade Percentage</h4>
                <ul style="list-style-type: none; padding-left: 0;">
                    <li><strong>By Distance:</strong> <span style="font-size: 18px; font-weight: bold; color: #4169E1;">{shade_percentage:.1f}%</span></li>
                    <li><strong>By Time:</strong> <span style="font-size: 18px; font-weight: bold; color: #4169E1;">{time_shade_percentage:.1f}%</span></li>
                </ul>
            </div>
            """

            # Calculate the middle point of the walk
            middle_index = len(walk) // 2
            middle_point = walk[middle_index]

            folium.Marker(
                location=(middle_point['lat'], middle_point['lon']),
                popup=folium.Popup(annotation, max_width=300),
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

def main():
    # Directory containing GPX files
    gpx_directory = 'gpx'

    # Process all GPX files in the directory
    all_waypoints = process_gpx_files(gpx_directory)

    # Create the shade map
    shade_map = create_shade_map(all_waypoints)

    if shade_map:
        # Save the map
        shade_map.save('index.html')
        print("Shade map has been generated and saved as 'index.html'")
    else:
        print("Failed to generate map. Please check your GPX files.")

if __name__ == "__main__":
    main()