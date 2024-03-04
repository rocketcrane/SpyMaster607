import math

def remap_range(value, left_min, left_max, right_min, right_max):
	# log addition
	log_left_min = math.log(left_min + 1e-5)
	log_left_max = math.log(left_max)
	log_value = math.log(value+1e-5)
	
	# this remaps a value from original (left) range to new (right) range
	# Figure out how 'wide' each range is
	left_span = log_left_max - log_left_min
	right_span = right_max - right_min
	
	# Convert the left range into a 0-1 range (int)
	valueScaled = float(log_value - log_left_min) / float(left_span)
	
	# Convert the 0-1 range into a value in the right range.
	return float(right_min + (valueScaled * right_span))
	
print(remap_range(0, 0, 65535, 0, 100))
print(remap_range(5000, 0, 65535, 0, 100))
print(remap_range(30000, 0, 65535, 0, 100))
print(remap_range(65535, 0, 65535, 0, 100))