#! /usr/bin/env python

# maintain maze state in 2d numpy array. Subscribe to /odom and /scan.
# Iterate through all 360 degrees and find (x,y) from 
# distances in /scan topic. Add some constant for each
# iteration that a particular grid has been exposed.

import rospy
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
import numpy as np
# import matplotlib.pyplot as plt
import message_filters
import tf
import math

class Maze:
  def __init__(self):
    # For debugging
    self.start_time = None

    self.d = 0.012 # Wall thickness in m
    self.s = 0.18-self.d # Side length of each grid square sans the walls
    self.N = 16 # Number of grid squares in one row
    # Ensure that: N*(s+d)+d = total side length of maze
    self.confidence_threshold = 10
    self.lower_thres = 0.2
    self.upper_thres = 0.8

    self.w = 2*self.N-1
    self.h = 2*self.N-1
    self.maze_size = [self.w, self.h]
    self.maze_state = np.zeros(self.maze_size)
    self.maze_state[1::2, 1::2] = 1 # Both i and j odd, lattice point
    self.maze_confidence = np.zeros(self.maze_size)
    self.maze_confidence[1::2, 1::2] = -1 # Both i and j odd
    self.maze_confidence[::2, ::2] = -1 # Both i and j even

    self.dest = [0,0]

  def remap(self, t):
    '''
    remaps from range [-N*(s+d)/2, N*(s+d)/2] to [0, N]
    t can be either {x_wall, y_wall}
    '''
    return t/(self.s+self.d) + self.N/2


  def updateFloodfillMatrix(self):
    pass


  def updateMazeConfidence(self, x, y):
    fx, ix = math.modf(x)
    fy, iy = math.modf(y)

    if (fx<self.lower_thres or fx>self.upper_thres) and (fy<self.lower_thres or fy>self.upper_thres):
      return
    
    elif (fx<self.lower_thres and ix==0) or \
         (fx>self.upper_thres and ix==self.N-1) or \
         (fy<self.lower_thres and iy==0) or \
         (fy>self.upper_thres and iy==self.N-1):
      return
    
    elif fx<self.lower_thres:
      X = ix*2 - 1
      Y = iy*2
    elif fx>self.upper_thres:
      X = ix*2 + 1
      Y = iy*2
    elif fy<self.lower_thres:
      X = ix*2
      Y = iy*2 - 1
    elif fy>self.upper_thres:
      X = ix*2
      Y = iy*2 + 1
    else:
      return

    X = int(X)
    Y = int(Y)
    
    # print("%f\t%f" % (X,Y))

    if self.maze_confidence[X,Y] == -1:
      rospy.logfatal("Trying to update non-updatable grid")
      return

    if (self.maze_confidence[X,Y] < self.confidence_threshold):
      self.maze_confidence[X,Y] += 1
      if (self.maze_confidence[X,Y] == self.confidence_threshold):
        self.maze_state[X,Y] = 1
        self.updateFloodfillMatrix()

 
  def mazeCallback(self, odom, scan):
    if (odom is not None and scan is not None):
      rospy.loginfo("Update requested")

      # Extract robot's (x,y,theta) from /odom
      x_bot = odom.pose.pose.position.x
      y_bot = odom.pose.pose.position.y
      quaternion = (
          odom.pose.pose.orientation.x,
          odom.pose.pose.orientation.y,
          odom.pose.pose.orientation.z,
          odom.pose.pose.orientation.w)
      rpy = tf.transformations.euler_from_quaternion(quaternion)
      theta_bot = rpy[2] - math.pi/2

      # Obtain (x,y) of laser end-points from /scan + /odom
      laser_ranges = scan.ranges
      no_of_points = len(laser_ranges)
      max_range = scan.range_max
      # increment = scan.angle_increment
      # angle_min = scan.angle_min # -3.40000009537
      # angle_max = scan.angle_max # 3.40000009537
      # no_of_points = int( (scan.angle_max - scan.angle_min)/scan.angle_increment )      

      # print("Bot pose: (%f,%f,%f)" % (x_bot, y_bot, theta_bot*180/math.pi))
      
      for i in range(no_of_points):
        angle = scan.angle_min + i*scan.angle_increment
        radial_distance = laser_ranges[i]
        if (radial_distance <= max_range): # Eliminate inf ranges(idk if this is actually needed, for safety)
          x_wall = x_bot + radial_distance*math.cos(theta_bot + angle)
          y_wall = y_bot + radial_distance*math.sin(theta_bot + angle)
          # print("Wall(laser): (%f,%f,%f)" % (x_wall, y_wall, (theta_bot + angle)*180/math.pi))
          # rospy.signal_shutdown("Debug over")
          # return

          # print("Global: %f\t%f" % (x_wall, y_wall))
          x_wall = self.remap(x_wall)
          y_wall = self.remap(y_wall)
          # print("[0,N]: %f\t%f" % (x_wall, y_wall))

          self.updateMazeConfidence(x_wall, y_wall)


      if (rospy.get_time()-self.start_time) > 50:
        print(self.maze_confidence[12:19,12:19])
        np.savetxt('debug-confidence.txt', self.maze_confidence, delimiter='\t', fmt='% .0f')
        np.savetxt('debug-state.txt', self.maze_state, delimiter='\t', fmt='% .0f')
        rospy.signal_shutdown("Time period over")

if __name__ == '__main__':
  try:
    rospy.init_node('maze_algorithms_node')#, disable_signals=True)
    maze_obj = Maze()
    maze_obj.start_time = rospy.get_time()
    while (rospy.get_time()==0): # Wait until nodes have loaded completely
      pass
    
    rospy.loginfo("Creating subscribers...")
    odom_sub = message_filters.Subscriber('/odom', Odometry)
    scan_sub = message_filters.Subscriber('/my_mm_robot/laser/scan', LaserScan)
    rospy.loginfo("Done")
    
    rospy.loginfo("Creating time synchronizer between odom and laser scan...")
    ts = message_filters.ApproximateTimeSynchronizer([odom_sub, scan_sub], queue_size=10, slop=0.1)
    ts.registerCallback(maze_obj.mazeCallback)
    rospy.loginfo("Done")
    
    rospy.loginfo("Spinning...")
    rospy.spin()

  except rospy.ROSInterruptException:
    rospy.loginfo("Node terminated")

# rospy.signal_shutdown("Debug over")