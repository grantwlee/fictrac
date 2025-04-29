import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from tkinter import filedialog, Tk
from datetime import datetime

def fileManagement():
    #ask which file to upload and what to save output as
    curDate = datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
    defaultFname = f'{curDate}.html'
    root = Tk()
    root.withdraw()
    fname = filedialog.askopenfilename(title='Select Fictrac .Dat File', 
                                       filetypes=[("dat files","*.dat"), 
                                                  ("csv files", "*.csv"), 
                                                  ("all files", "*.*")])
    
    filepath = filedialog.asksaveasfilename(title='Save File',
                                            defaultextension= '.html',
                                            initialfile = defaultFname)
    
    root.destroy() 
    return(fname, filepath)
    
def processData(fname, radiuscm):

    #add in data headers, fictrac produces a .dat file with no headers
    column_names = ['frame counter', 'cam delta rotation vector x', 
                    'cam delta rotation vector y', 'cam delta rotation vector z', 
                    'delta rotation error score', 'lab delta rotation vector x', 
                    'lab delta rotation vector y', 'lab delta rotation vector z', 
                    'cam absolute rotation vector x', 'cam absolute rotation vector y', 
                    'cam absolute rotation vector z', 'lab absolute rotation vector x', 
                    'lab absolute rotation vector y', 'lab absolute rotation vector z', 
                    'lab integrated x position', 'lab integrated y position', 
                    'integrated animal heading', 'animal direction movement', 
                    'animal movement speed', 'integrated forward motion', 
                    'integrated side motion', 'timestamp',
                    'sequence counter', 'delta timestamp', 'alt. timestamp' ]
    
    try:
        df = pd.read_csv(fname, names=column_names)
    except FileNotFoundError:
        return None
    except pd.errors.EmptyDataError:
        return None

    #drop unused columns that are not relevant because of the fact that the cricket is able to rotate
    df = df.drop(columns=['lab integrated x position', 'lab integrated y position', 
                    'integrated animal heading', 'animal direction movement', 
                    'cam absolute rotation vector x', 'cam absolute rotation vector y',
                    'cam absolute rotation vector z', 'lab absolute rotation vector x', 
                    'lab absolute rotation vector y', 'lab absolute rotation vector z',
                    'cam delta rotation vector x', 'cam delta rotation vector y',
                    'cam delta rotation vector z', 'lab delta rotation vector x',
                    'lab delta rotation vector y', 'lab delta rotation vector z',
                    ])

    #scale all relevant columns to cm by using radius of trackball
    df['integrated forward motion'] *= radiuscm
    df['integrated side motion'] *= radiuscm
    df['animal movement speed'] *= radiuscm

    #convert timestamps to seconds from ms and make sure timestamp starts 0 for beginning of session
    df['timestamp'] = df['timestamp'] - df['timestamp'].iloc[0]
    df['timestamp'] = df['timestamp']/1000
    df['delta timestamp'] = df['delta timestamp']/1000

    #changes speed from cm/frame to cm/s
    df['animal movement speed'] = df['animal movement speed']/df['delta timestamp']

    #creates a measure of acceleration in cm/s^2
    delta_v = df['animal movement speed'].diff()
    delta_t = df['timestamp'].diff()
    df['acceleration'] = (delta_v / delta_t).fillna(0)

    #measures average velocity
    avgvel = df['animal movement speed'].mean()

    #calculate distance walked per frame, integrated forward motion is cumulative
    df['x per frame'] = df['integrated side motion'].diff().fillna(0)
    df['y per frame'] = df['integrated forward motion'].diff().fillna(0)
    df['dist per frame'] = np.sqrt((df['x per frame'])**2 + (df['y per frame'])**2)


    #compute the angle of movement from one frame to the next
    df['angular orientation'] = np.degrees(np.arctan2(
        df['y per frame'],
        df['x per frame']
        ))
    df['angular orientation'] = df['angular orientation'].fillna(0)
    #set 0 degrees as towards the speaker/+Y
    df['angular orientation'] = df['angular orientation'] - 90
    #wrap so angles reach [-180, 180] and switch negative angles to left and positive to right
    df['angular orientation'] = ((df['angular orientation'] + 180) % 360 - 180) * -1

    #final angular orientation with same adjustment as above
    finalX, finalY = df[['integrated side motion', 'integrated forward motion']].iloc[-1]
    finalAngle = np.degrees(np.arctan2(finalY, finalX))
    finalAngle = (finalAngle - 90)
    finalAngle = ((finalAngle + 180) % 360 - 180)* -1

    #calculate distance walked towards, away and net from the speaker. add the distance walked in blanks
    towards = df[(df['angular orientation']<=60) & (df['angular orientation']>=-60)]['dist per frame'].sum()
    away = df[(df['angular orientation'] > 60) | (df['angular orientation']< -60)]['dist per frame'].sum()
    total = towards+away

    return(df, avgvel, towards, away, total, finalAngle)

def makegraph(df, filepath, avgvel, towards, away, total, finalAngle, radiuscm):
    
    day = datetime.now().strftime("%m/%d/%Y")
    top25thresh = df['acceleration'].quantile(0.75)
    top50thresh = df['acceleration'].quantile(0.50)
    dftop25 = df[df['acceleration'] >= top25thresh]
    dftop50 = df[df['acceleration'] >= top50thresh]

    size = df[['integrated forward motion', 'integrated side motion']].abs().max().max().round()
    size = size + (size*0.1)

    px_graph = px.line(df, x='integrated side motion', y='integrated forward motion', 
                        labels = {
                            'integrated side motion': '',
                            'integrated forward motion': ''
                        },
                        hover_data={
                        'acceleration': False,
                        'integrated side motion': False,
                        'integrated forward motion': False},
                        range_x=[-size,size],
                        range_y=[-size,size],
                    )

    px_graph.update_traces(customdata=df[['timestamp', 'acceleration', 'animal movement speed', 'angular orientation']],
                            hovertemplate="<b>Timestamp: %{customdata[0]:.2f} s</b><br>" +
                            "<b>Speed: %{customdata[2]:.2f} cm/s</b><br>" +
                            "<b>Acceleration: %{customdata[1]:.2f} cm/s²</b><br>" +
                            "<b>Angular orientation: %{customdata[3]:.2f}°</b><br>" +
                            "<extra></extra>",)

    px_graph.add_trace(go.Scatter(
        x=dftop25['integrated side motion'],
        y=dftop25['integrated forward motion'],
        mode='markers',
        marker=dict(
            size=6,
            color='red',
            opacity=0.6,
            line=dict(width=1, color='black')
        ),
        name='Top 25% Acceleration',
        visible=False,
        customdata=dftop25[['timestamp', 'acceleration', 'animal movement speed', 'angular orientation']],
        hovertemplate="<b>Timestamp: %{customdata[0]:.2f} s</b><br>" +
                    "<b>Speed: %{customdata[2]:.2f} cm/s</b><br>" +
                    "<b>Acceleration: %{customdata[1]:.2f} cm/s²</b><br>" +
                    "<b>Angular orientation: %{customdata[3]:.2f}°</b><br>" +
                    "<extra></extra>"))

    px_graph.add_trace(go.Scatter(
        x=dftop50['integrated side motion'],
        y=dftop50['integrated forward motion'],
        mode='markers',
        marker=dict(
            size=6,
            color='orange',
            opacity=0.6,
            line=dict(width=1, color='black')
        ),
        name='Top 50% Acceleration',
        visible=False,
        customdata=dftop50[['timestamp', 'acceleration', 'animal movement speed', 'angular orientation']],
        hovertemplate="<b>Timestamp: %{customdata[0]:.2f} s</b><br>" +
                    "<b>Speed: %{customdata[2]:.2f} cm/s</b><br>" +
                    "<b>Acceleration: %{customdata[1]:.2f} cm/s²</b><br>" +
                    "<b>Angular orientation: %{customdata[3]:.2f}°</b><br>" +
                    "<extra></extra>"))
    
    px_graph.add_annotation(
        text=f"Total path length: {total:.2f} cm",
        xref="paper", yref="paper",
        x=1.04, y=0.95,  
        showarrow=False,
        font=dict(size=14, color="black"),
        bgcolor="lightgray",
        bordercolor="black",
        borderwidth=1,
        xanchor='left'
    )


    px_graph.add_annotation(
        text=f"Towards speaker: {towards:.2f} cm",
        xref="paper", yref="paper",
        x=1.04, y=.9, 
        showarrow=False,
        font=dict(size=14, color="black"),
        bgcolor="lightgray",
        bordercolor="black",
        borderwidth=1,
        xanchor='left'
    )

    px_graph.add_annotation(
        text=f"Away from speaker: {away:.2f} cm",
        xref="paper", yref="paper",
        x=1.04, y=0.85,  
        showarrow=False,
        font=dict(size=14, color="black"),
        bgcolor="lightgray",
        bordercolor="black",
        borderwidth=1,
        xanchor='left'
    )

    px_graph.add_annotation(
        text=f"Final angular orientation: {finalAngle:.2f}°",
        xref="paper", yref="paper",
        x=1.04, y=0.8, 
        showarrow=False,
        font=dict(size=14, color="black"),
        bgcolor="lightgray",
        bordercolor="black",
        borderwidth=1,
        xanchor='left'
    )

    px_graph.add_annotation(
        text=f"Average velocity: {avgvel:.2f} cm/s",
        xref="paper", yref="paper",
        x=1.04, y=.75, 
        showarrow=False,
        font=dict(size=14, color="black"),
        bgcolor="lightgray",
        bordercolor="black",
        borderwidth=1,
        xanchor='left'
    )

    px_graph.add_annotation(
        text=f"Trackball size: {radiuscm:.2f} cm",
        xref="paper", yref="paper",
        x=1.04, y=0, 
        showarrow=False,
        font=dict(size=14, color="black"),
        xanchor='left'
    )

    px_graph.update_layout(autosize = True,
                        yaxis_scaleanchor = 'x',
                        margin=dict(t=50,r=350),
                        xaxis_title="x position (cm)",
                            yaxis_title="y position (cm)",
                            title = {'text': f'Fictive Path of Animal<br><sup>Date: {day}</sup>',
                                    'x': 0.062,
                                    'y': 0.962,  
                                    'xanchor': 'left', 
                                    'yanchor': 'top', 
                                    'font': {'size': 22}  
                                }
                            )

    px_graph.update_layout(
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                x=1.0,
                y=1.06,
                xanchor="right",
                showactive=True,
                buttons=[
                    dict(
                        label="Path only",
                        method="update",
                        args=[{"visible": [True, False, False]}]  # Only path is visible
                    ),
                    dict(
                        label="Top 25% Accel values",
                        method="update",
                        args=[{"visible": [True, True, False]}]  # Path + top 25% markers
                    ),
                    dict(
                        label="Top 50% Accel values",
                        method="update",
                        args=[{"visible": [True, False, True]}]  # Path + top 50% markers
                    )
                ]
            )
        ]
    )

    px_graph.show()
    px_graph.write_html(filepath)

def main():
    fname, filepath = fileManagement()
    #radiuscm = radius of trackball, change this number to match your trackball
    radiuscm = 9.5
    df, avgvel, towards, away, total, finalAngle = processData(fname, radiuscm)
    makegraph(df, filepath, avgvel, towards, away, total, finalAngle, radiuscm)

if __name__ == "__main__":
    main()


