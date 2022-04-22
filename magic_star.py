import warnings, subprocess, sys
import numpy as np
import astropy as ap
# import matplotlib.pyplot as plt
from astropy.timeseries import LombScargle
# from matplotlib import colors
from astropy.io import fits
from scipy.ndimage import rotate
from scipy.special import erf
from astropy.wcs import WCS
from astropy.wcs import utils
from astropy.coordinates import SkyCoord
from astropy import units as u

from astropy.utils.exceptions import AstropyWarning

try:
	f_name = sys.argv[1]
	l_from_input = sys.argv[2]
	a_from_input = sys.argv[3]
except Exception as e:
	print(e)

# plt.rcParams.update({'figure.max_open_warning': 0})
warnings.simplefilter('ignore', AstropyWarning)

# initializing all directories
import os
from os.path import isdir, isfile, join
directory = './'	
dir_names = [directory+f+'/' for f in os.listdir(directory) if isdir(join(directory,f))] 

input_file = np.loadtxt('input.csv', dtype=object, skiprows=1, usecols=(i for i in range(25)), delimiter=',')

se_dir   = './SEoutput/'
se_files = [se_dir+f for f in os.listdir(se_dir) if isfile(join(se_dir,f))]

mins = {'g':100, 'r': 150, 'i': 250}

from scipy.optimize import curve_fit
from scipy.optimize import least_squares

# rotate points by angle a [degrees]
# pyplot rotation: origin (0,0) is to pleft of image. +x to the right, +y down
def point_rotation(x,y,a,img,img_rot):
	a = -a * np.pi/180
	x_0, y_0 = 0, 0
	x_0_, y_0_ = img.shape[0]*np.abs(np.sin(a)), img.shape[1]*np.abs(np.sin(a))
	x_, y_ = np.array((x-x_0)*np.cos(a) - (y-y_0)*np.sin(a), dtype=int), np.array((x-x_0)*np.sin(a) + (y-y_0)*np.cos(a), dtype=int)
	# to account for direction of rotation
	if   a>0: x_+= int(x_0_)
	elif a<0: y_+= int(y_0_)

	if x_<0: x_=0
	if y_<0: y_=0

	return x_, y_

# b if given is the mean background per pixel
def take_lightcurve(img, trail_start, trail_end, fwhm=4, b=None, height_correction=None, display=False, err=False):
	obj_width = fwhm
	sky_width = 2*fwhm

	if height_correction is not None:
		trail_start[1] -= height_correction
		trail_end[1]   += height_correction

	obj_rect  = img[int(trail_start[1]):int(trail_end[1]), int(trail_start[0]-obj_width):int(trail_start[0]+obj_width)]

	sky_left  = img[int(trail_start[1]):int(trail_end[1]), int(trail_start[0]-obj_width-sky_width):int(trail_start[0]-obj_width)]
	sky_right = img[int(trail_start[1]):int(trail_end[1]), int(trail_start[0]+obj_width):int(trail_start[0]+obj_width+sky_width)]

	obj_row_sums = np.array([np.sum(i) for i in obj_rect])
	sky_left_row_sum  = np.array([np.sum(i) for i in sky_left ])
	sky_right_row_sum = np.array([np.sum(i) for i in sky_right])
	sky_row_avg = (sky_right_row_sum+sky_left_row_sum)/(sky_right.shape[1]+sky_left.shape[1])

	if b is not None:
		sky_row_avg = b

	obj_minus_sky = obj_row_sums - sky_row_avg * obj_rect.shape[1]

	sigma_row = obj_minus_sky + (len(obj_row_sums)) * (sky_row_avg + hdr['RDNOISE']**2) + (len(obj_row_sums))**2 * sky_row_avg**.5 # from magnier
	sigma_row = sigma_row ** .5

	if display:
		plt.figure()
		t = np.arange(len(obj_minus_sky))
		plt.scatter(t, obj_minus_sky)

	r = [obj_minus_sky]
	if err: 
		r.append(sigma_row)
		r.append(sky_row_avg)
	return r

#assuming vertical streaks for drawing rectangles and moving down 
def trail_spread_function(img, trail_start, trail_end, obj_width=25, display = False):
		
	obj_rect = img[int(trail_start[1]):int(trail_end[1]), int(trail_start[0]-obj_width):int(trail_start[0]+obj_width)]

	col_sums = np.sum(obj_rect, axis=0)
		
	# col_sums /= np.max(col_sums)
	rect_width = np.arange(0, 2*obj_width, 1)
	param_vals, param_covs = curve_fit(model, rect_width, col_sums, p0=[3, obj_width, .03, 60000, 20000, -3])

		

	# ax[2].scatter(rect_width, col_sums, label='column sums')
	# ax[2].plot(rect_width, model(rect_width, *param_vals), label='model fit')
	# ax[2].legend()
	return param_vals, param_covs

def model(x, s, m, a, c, b, d):
	return c*np.exp(-.5* ((x-m)/s)**2) + a*x + b + d*x**2

def quadratic(x, a, b, c, d, e):
	return a*x**2 + b*x + c + d*x**3 + e*x**4

# def star_box_model(x, t_1, t_2, a,b,c,d,e,f,g, a_1,b_1,c_1,d_1,e_1,f_1,g_1):
# def star_box_model(x, t_1, t_2, a,b,c,d,e,f,g,back):
def box_model_sine(x, t_1, t_2, a, w, d, c, s):
	r = np.zeros(x.shape) + s
	filt = np.where((x<=t_2) & (x>=t_1))
	r[filt] = a * np.sin(w*x[filt]+d) + c
	return r

def box_model_(x, t_1, t_2, s_1, s_2):
	r = np.zeros(x.shape) + s_2
	r[np.where((x<=t_2) & (x>=t_1))] = s_1
	return r


def box_model(x, t_1, t_2, s_1):
	r = np.zeros(x.shape) 
	r[np.where((x<=t_2) & (x>=t_1))] = s_1
	return r


def fourier(x, *params):
    params = np.array(params).reshape(-1,3)
    a = params[:, 0]
    b = params[:, 1]
    c = params[:, 2]
    ret = a[0] * np.sin(np.pi / b[0] * x) + c[0]
    for deg in range(1, len(a)):
        ret += a[deg] * np.sin((deg+1) * np.pi / b[deg] * x) + c[deg]
    return ret

img_rot, centroid, = 0, 0
count = 0

# Veres 2012 eq 3
# r = [x,y], s = sigma, L is length, a is angle, b is background noise (holding constant for now)
# img_rot and centroid are not fitting variables - want to pass these in as constants; centroid = [x,y]
def trail_model(x, y, s, L, a, b_1, x_0, y_0):

	global img_rot, star_x_ext, star_y_ext, centroid
	
	L_but_longer = L*1
	s_but_wider  = s*1

	# trail = img_rot[int(c_y-L/2+0.5):int(c_y+L/2+.5) , int(c_x-s*2.355+.5): int(c_x+s*2.355+.5) ]
	trail = img_rot[int(y_0 - L_but_longer/2):int(y_0 + L_but_longer/2) , int(x_0 - s_but_wider*2.355):int(x_0 + s_but_wider*2.355)]
	# print( 'trail shape', trail.shape)

	flux   = np.sum(trail)
	a      = (a) * np.pi/180
	cosine = np.cos(a)
	sine   = np.sin(a)

	flux_term   = flux/(L * 2 * s * (2 * np.pi)**.5)
	exponential = np.exp( -(( (x-x_0)*sine + (y-y_0)*cosine )**2 ) / (2*s**2) )
	erf1 = erf(( (x-x_0) * cosine + (y-y_0) * sine + L/2) / (s*2**.5)) 
	erf2 = erf(( (x-x_0) * cosine + (y-y_0) * sine - L/2) / (s*2**.5))
	background = b_1 

	return flux_term * exponential * (erf1-erf2) + background

def draw_model(s, L, a, b_1, c_x, c_y):

	global img_rot, star_x_ext, star_y_ext, centroid

	# dont actually know if this meshgrid business works??? come back to this first if breaks
	# xx, yy = np.meshgrid(np.arange(0, img_rot.shape[1]), np.arange(0, img_rot.shape[0]))
	xx, yy = np.meshgrid( np.arange(0, img_rot.shape[1]), np.arange(0, img_rot.shape[0]) )

	model = trail_model(xx, yy, s, L, a, b_1, c_x, c_y)	#assuming this is 2FWHM wide and 2L tall

	# print(img.shape, rotate(img,-a).shape)
	return model
	

def residual(par):
	global img_rot, star_x_ext, star_y_ext, centroid
	s, L, a, b_1, x_0, y_0 = par[0], par[1], par[2], par[3], par[4], par[5]
	
	model = draw_model(s, L, a, b_1, x_0, y_0)

	# L_but_longer = L*1.2
	s_but_wider  = s

	box_y_width = np.abs(star_y_ext[1] - star_y_ext[0]) * 1.2

	# observed = img_rot[int(y_0 - L_but_longer/2):int(y_0 + L_but_longer/2) , int(x_0 - s_but_wider*2.355):int(x_0 + s_but_wider*2.355)]
	observed = img_rot[int(centroid[1] - box_y_width/2):int(centroid[1] + box_y_width/2) , int(centroid[0] - s_but_wider*2*2.355):int(centroid[0] + s_but_wider*2*2.355)]
	# observed_row_sums = np.array([np.sum(i) for i in observed])
	# observed_col_sums = np.sum(observed, axis=0)

	# model_slice = model[int(y_0 - L_but_longer/2):int(y_0 + L_but_longer/2) , int(x_0 - s_but_wider*2.355):int(x_0 + s_but_wider*2.355)]
	model_slice = model[int(centroid[1] - box_y_width/2):int(centroid[1] + box_y_width/2) , int(centroid[0] - s_but_wider*2*2.355):int(centroid[0] + s_but_wider*2*2.355)]
	# model_row_sums = np.array([np.sum(i) for i in model_slice])
	# model_col_sums = np.sum(model_slice, axis=0)

	# print(model_slice.shape, observed.shape)
	# print()
	# print(model.shape)
	# print(observed.shape)

	r = np.sqrt(np.sum(model_slice-observed)**2)
	# r = np.sqrt( (model_row_sums-observed_row_sums)**2 ) 
	# r = np.sqrt((model_col_sums-observed_col_sums)**2)

	return r

if __name__ == '__main__':
	
	for d in dir_names:
		file_names = [d+f for f in os.listdir(d) if isfile(join(d,f))]
		yea = False

		# if not ('XD169' in d): continue
		if not f_name in d: continue
		#if not ('2015_TG24' in d or '2016_NM15' in d or '2015_VH1' in d): continue

		start_times = []
		lightcurves = []

		# fig_ast, ax_ast = plt.subplots()
		# ax_ast.set_xlabel('Julian date')

		for f in file_names:
			try:
				file = fits.open(f)
				print(f)
			except Exception as e:
				print(f)
				continue
			hdr = file[0].header
			img = file[0].data

			exp_time = float(hdr['EXPMEAS'])


			# object id from directory name --> string splicing
			obj_id = f.split('_')
			obj_id = obj_id[0][2:] + ' ' + obj_id[1]

			# plt.figure()
			# fig, ax = plt.subplots(1,3)
			# ax[0].set_title(f)
			# ax[0].imshow(img, cmap='gray', norm=colors.LogNorm(vmin=mins[hdr['FILTER'][0]]))

			obj_rows = input_file[np.where(input_file[:,1]==obj_id),:][0]
			
			
			try:
				obj = obj_rows[np.where(obj_rows[:,0]==f.split('/')[-1])][0]
				trail_start = np.array(obj[-4:-2], dtype=int)
				trail_end	= np.array(obj[-2:], dtype=int)
				start_time  = float(obj[6])
			except Exception as e:
				print(f,obj[-4:-2],obj[-2:])
				# plt.close()
				continue

			
			angle = -1*np.arctan2(trail_end[0]-trail_start[0], trail_end[1]-trail_start[1]) * 180/np.pi
			img_rotated = rotate(img, angle)
			# ax[0].imshow(img_rotated, cmap='gray', norm=colors.LogNorm(vmin=mins[hdr['FILTER'][0]]))

			trail_start = np.array(point_rotation(trail_start[0], trail_start[1], angle, img, img_rotated), dtype=int)
			trail_end	= np.array(point_rotation(trail_end[0]  , trail_end[1]  , angle, img, img_rotated), dtype=int)
			trail_length = trail_end[1] - trail_start[1]

			
			trail_spread, trail_spread_covs = trail_spread_function(img_rotated, trail_start, trail_end, display=False)
			fwhm = int(trail_spread[0] * 2.355)

			centroid_deviation = -fwhm + trail_spread[1] # if negative, trail is to the left, if positive, trail to right
			

			# correcting trail start/end
			trail_start[0] += int(centroid_deviation+.5)
			trail_end[0]   += int(centroid_deviation+.5)

			trail_centroid = np.array([trail_start[0], np.mean([trail_start[1], trail_end[1]])])

			print('trail length: ', trail_length)


			# ASTEROID TRAIL FITTING
			img_rot = img_rotated
			centroid = trail_centroid
			star_x_ext = [trail_centroid[0] - fwhm, trail_centroid[0] + fwhm]
			star_y_ext = [trail_start[1], trail_end[1]]

			p0 = np.array([4, trail_length, 90, 200, trail_centroid[0], trail_centroid[1]])
			param_bounds = ([1, trail_length/2, -180, 0, 0, 0], [15, trail_length*5, 180, 2e3, img_rotated.shape[1], img_rotated.shape[0] ])

			fit = least_squares(residual, p0, loss='linear', ftol=0.05, xtol=0.05, gtol=0.05, bounds=param_bounds)
			print('asteroid initial residual: ', residual(p0))
			print('asteroid fit residual: ' , residual(fit.x))

			fwhm = fit.x[0] * 2.355
			trail_length = fit.x[1]
			height_correction = int(trail_length * .2 + .5) # 20% more rows above and below to get some sky 
			height_correction = 0
			trail_centroid = np.array([fit.x[4], fit.x[5]])

			trail_start = np.array([trail_centroid[0] , trail_centroid[1] - trail_length/2])
			trail_end   = np.array([trail_centroid[0] , trail_centroid[1] + trail_length/2])


			# asteroid trail length in 70o13 is 101 tall
			# ax[0].plot([trail_start[0], trail_end[0]], [trail_start[1], trail_end[1]], marker='*')

			obj_minus_sky, sigma_row, sky_row_avg = take_lightcurve(img_rotated, trail_start, trail_end, fwhm=fwhm, b=None, height_correction=height_correction, display=False, err=True)

			# x = np.arange(0, 101, 101/len(obj_row_sums))
			x = np.arange(0, len(obj_minus_sky), 1)
			# ax[1].plot(x, obj_minus_sky)

			# UNCOMMENT LATER, maybe
			# ax[1].errorbar(x, obj_minus_sky, yerr = sigma_row, fmt='r', capsize=3, linewidth=2, elinewidth=1, alpha=.6)

			# WCS stuff
			w = WCS(hdr)
			c = SkyCoord(f'{obj[7]} {obj[8]}', unit=(u.deg, u.deg))
			target_x, target_y = np.round(utils.skycoord_to_pixel(c, w))
			
			# source extractor !!
			# sex = subprocess.run(['sex', f, '-DETECT_MINAREA', str(trail_length*fwhm), '-CATALOG_NAME', '_'.join(f.split("/")[1:])[:-4] + '.cat'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
			try:
				se_index = [x for x in se_files if (f.split('/')[1] in x and f.split("/")[2].split(".")[0] in x)][0]
			except Exception as e:
				print(e)
				continue


			sex_output = np.loadtxt(se_index, skiprows=9)
			print('SExtractor found stars: ',sex_output.shape[0])
			star_x = sex_output[:,5]
			star_y = sex_output[:,6]

			star_x_min = sex_output[:,1]
			star_y_min = sex_output[:,2]
			star_x_max = sex_output[:,3]
			star_y_max = sex_output[:,4]

			dist_to_asteroid = []

			# to rotate to asteroid's reference -- SExtractor works with raw fits file data
			for i in range(len(star_x)):
				star_x[i], star_y[i] = point_rotation(star_x[i], star_y[i], angle, img, img_rotated)
				dist_to_asteroid.append((star_x[i] - trail_centroid[0])**2 + (star_y[i] - trail_centroid[1])**2)
				star_x_min[i], star_y_min[i] = point_rotation(star_x_min[i], star_y_min[i], angle, img, img_rotated)
				star_x_max[i], star_y_max[i] = point_rotation(star_x_max[i], star_y_max[i], angle, img, img_rotated)
				# print(star_x[i], star_y[i])

			# filtering based on distance to asteroid
			dist_to_asteroid = np.array(dist_to_asteroid)
			dist_sorted = np.argsort(dist_to_asteroid)

			star_x     = star_x[dist_sorted]
			star_y     = star_y[dist_sorted]
			star_x_min = star_x_min[dist_sorted]
			star_y_min = star_y_min[dist_sorted]
			star_x_max = star_x_max[dist_sorted]
			star_y_max = star_y_max[dist_sorted]

			# filtering bad stars from sextractor
			bad_stars = np.where((star_x<trail_length) | (star_x>img_rotated.shape[1]-trail_length) | (star_y<trail_length) | (star_y>img_rotated.shape[0]-trail_length)) # too close to edge
			bad_stars = np.append(bad_stars, 0) # want to get rid of asteroid too
			# bad_stars = np.append(bad_stars, np.where((star_x<trail_start[0]+fwhm) & (star_x>trail_start[0]-fwhm) & (star_y<trail_end[1]) & (star_y>trail_start[1]))) # want to get rid of asteroid too
			print('filter on sextractor', len(bad_stars))
			star_x     = np.delete(star_x, bad_stars, 0)
			star_y     = np.delete(star_y, bad_stars, 0)
			star_x_min = np.delete(star_x_min, bad_stars, 0)
			star_y_min = np.delete(star_y_min, bad_stars, 0)
			star_x_max = np.delete(star_x_max, bad_stars, 0)
			star_y_max = np.delete(star_y_max, bad_stars, 0)


			L_0 = ((star_x_max-star_x_min)**2 + ((star_y_max-star_y_min)))**.5
			# to rotate image -- negative angle from vertical
			a_0 = -1*np.arctan2( star_x_max-star_x_min,  star_y_max-star_y_min) * 180/np.pi

			l = float(l_from_input)
			a = float(a_from_input)
			
			L_0 = np.ones(L_0.shape) * l
			a_0 = np.ones(L_0.shape) * a
			
			# f_stars, ax_stars = plt.subplots(3, 5)
			# f_stars_sm, ax_stars_sm = plt.subplots(3, 5)
			cheats_on = False

			try:
				# star parametsrs
				cheat_codes = np.loadtxt(f'{f[:-4]}_params.txt')
				cheats_on   = True
			except Exception as e:
				print('Invalid cheat code: ', e, cheats_on)
			
			stars        = []
			trail_starts = []
			trail_ends   = []
			residuals    = []

			row_sums = []
			row_sums_smooth = []

			i = 0
			while True:
			# for i in range(len(star_x)):
			# for i in range(1):
				if i >= len(star_x) or i == 50: break

				centroid = star_x[i], star_y[i]
				# x_correction = (star_x_min[i] - star_x_max[i])*.10
				# y_correction = (star_y_min[i] - star_y_max[i])*.10
				x_correction, y_correction = 0,0
				star_x_ext = int(star_x_min[i]-x_correction), int(star_x_max[i]+x_correction)
				star_y_ext = int(star_y_min[i]-y_correction), int(star_y_max[i]+y_correction)
				# print(centroid, star_x_ext, star_y_ext)

				img_star_rotated = rotate(img_rotated, a_0[i])
				img_rot = img_star_rotated # setting the global variable img_rot for trail fitting

				centroid   = point_rotation(centroid[0], centroid[1], a_0[i], img_rotated, img_star_rotated)
				upper_left = point_rotation(star_x_min[i] , star_y_min[i] , a_0[i], img_rotated, img_star_rotated)
				lower_rite = point_rotation(star_x_max[i] , star_y_max[i] , a_0[i], img_rotated, img_star_rotated)

				# setting global variables to predefine how big the star fitting box is, *only lengthwise, because fitting width with fwhm
				star_x_ext = upper_left[0], lower_rite[0]
				star_y_ext = upper_left[1], lower_rite[1]

				p0 = np.array([3, L_0[i], 90, np.mean(sky_row_avg), centroid[0], centroid[1]])

				param_bounds = ([1, L_0[i]/2, -180, 0, 0, 0], [10, L_0[i]*5, 180, 2e3, img_star_rotated.shape[1], img_star_rotated.shape[0] ])

				try:
					if cheats_on and False:
						param = cheat_codes[i]
						r_fit = residual(param)
						print('hell ofa cheat code')
					else: 
						fit = least_squares(residual, p0, loss='linear', ftol=0.05, xtol=0.05, gtol=0.05, bounds=param_bounds)
						r_fit = residual(fit.x)
						param = fit.x
				except Exception as e:
					print(f, i, e)
					i+=1
					# if i >= len(star_x): break
					continue
				
				# residuals.append([r_p0, r_p0])
				r_p0  = residual(p0)
				residuals.append([r_p0, r_fit])
				# print('p0:', p0)
				print('residual(p0) : ' , r_p0, p0)
				print('residual(fit): ' , r_fit, param)

				
				s, L, a, b, x_0, y_0 = param[0], param[1], param[2], param[3], param[4], param[5]
				# s, L, a, b, x_0, y_0 = p0[0], p0[1], p0[2], p0[3], p0[4], p0[5]
				
				# keeping it rotated to star's reference, so don't actually need to go back to asteroid 
				star_trail_start = np.array([x_0, y_0 - L/2])
				star_trail_end   = np.array([x_0, y_0 + L/2])

				fwhm = s * 2.355
				str_minus_sky, sigma_row, str_sky_avg = take_lightcurve(img_star_rotated, star_trail_start, star_trail_end, fwhm=fwhm, display=False, err=True)
				
				# yet another binning attempt --> linear interpolation
				smooth_x = np.linspace(0, int(L), int(trail_length))
				# print(smooth_x.shape)
				# smoothed = np.interp(smooth_x, np.arange(0, len(str_minus_sky), 1), str_minus_sky)
				# smoothed = np.median([np.roll(A,-2),np.roll(A,-1),np.roll(A,1),np.roll(A,2)],axis=0)
				star_to_asteroid = L/trail_length
				N = int( star_to_asteroid * 4 + 0.5)
				smoothed = []
				for j in range(trail_length):
					t = int(j*star_to_asteroid + .5)
					start_ind, end_ind = 0,0
					if t<N: 				# too close to start of trail
						start_ind, end_ind = 0, t+N+1
					elif t>=L-N: # too close to end of trail
						start_ind, end_ind = t-N-1, L-1
					else: 					# juuuust right
						start_ind, end_ind = t-N, t+N
					smoothed.append(np.median(str_minus_sky[start_ind:end_ind]))

				print('smooth shape: ', smoothed.shape)
				# smooth_norm = np.max(smoothed)
				# smoothed = np.array(smoothed)
				
				row_sums_smooth.append(smoothed)
				trail_starts.append(star_trail_start)
				trail_ends  .append(star_trail_end  )
				# img_stars   .append(img_star_rotated)
				stars       .append(param)
				
				print(' ')
				i+=1
		
				
			row_sums_smooth = np.array(row_sums_smooth)

			stars 		 = np.array(stars)
			residuals    = np.array(residuals)
			trail_starts = np.array(trail_starts)
			trail_ends   = np.array(trail_ends)

			print('initially, ', stars.shape[0])

			s_std        = np.std(stars[:,0])
			length_std   = np.std(stars[:,1])
			angle_std    = np.std(stars[:,2])

			s_mean  	 = np.mean(stars[:,0])
			length_mean  = np.mean(stars[:,1])
			angle_mean   = np.mean(stars[:,2])

			# throwing away outliers, ig. 
			# TODO: fit more stars and increase threshold? 
			threshold = 2 # sigmas

			star_filter  = np.where( (stars[:,0]<=s_mean+threshold*s_std) & (stars[:,0]>=s_mean-threshold*s_std) & (stars[:,1]<=length_mean+threshold*length_std) & (stars[:,1]>=length_mean-threshold*length_std) & (stars[:,2]<=angle_mean+threshold*angle_std) & (stars[:,2]>=angle_mean-threshold*angle_std) )
			stars        = stars       [star_filter]
			trail_starts = trail_starts[star_filter]
			trail_ends   = trail_ends  [star_filter]
			residuals    = residuals   [star_filter]

			row_sums_smooth = row_sums_smooth[star_filter]
			print('filtering: ', stars.shape[0])

			# sorting by residuals from biiiig fit
			res_filter   = np.argsort(residuals[:,1])
			residuals    = residuals   [res_filter]
			stars        = stars       [res_filter]
			trail_starts = trail_starts[res_filter]
			trail_ends   = trail_ends  [res_filter]

			row_sums_smooth = row_sums_smooth[res_filter]

			
			# ax[0].plot([trail_starts[:,0], trail_ends[:,0]], [trail_starts[:,1], trail_ends[:,1]], 'y*', ms=3 )

			# ax[0].scatter(star_x, star_y, c='orange', s=2, label='centroid')
			# ax[0].scatter(star_x_min, star_y_min, c='green', s=2, label='mins')
			# ax[0].scatter(star_x_max, star_y_max, c='purple', s=2, label='maxes')
			# ax[0].legend()

			# residuals = []

			#print('residuals argsort', r_sort)
			np.savetxt(f'{f[:-4]}_params.txt', stars)

			# row_sums = np.array(row_sums, dtype=object)
			# row_sums_smooth = np.array(row_sums_smooth, dtype=object)[r_sort] # type object for ragged nested sequences
			row_sums_smooth = row_sums_smooth[:10]

			#for k in row_sums_smooth: print(k)
			print('row_sums_smooth shape: ', row_sums_smooth.shape)

			# row_medians = np.median(row_sums, axis=0)
			#row_avgs_smooth = np.median(row_sums_smooth, axis=0)
			row_avgs_smooth = np.nanmedian(row_sums_smooth, axis=0)
			# row_avgs_smooth = np.array(row_avgs_smooth, dtype=float)

			# star_height_correction = int(np.median(stars[:,1])*.2+.5)
			# intensity_guess = np.median(row_avgs_smooth[star_height_correction:int(trail_length-star_height_correction)])
			# param_star, param_covs_star = curve_fit(box_model, np.arange(len(row_avgs_smooth)), row_avgs_smooth, p0=[star_height_correction,int(trail_length-star_height_correction),intensity_guess])
			# norm = param_star[2]

			norm = np.nanmedian(row_avgs_smooth)
			row_avgs_smooth/=norm

			# lightcurve of asteroid -- no height correction 
			# obj_minus_sky, sigma_row, sky_row_avg = take_lightcurve(img, trail_start, trail_end, fwhm=fwhm, display=False, err=True)

			ast_start = int(height_correction+.5)
			ast_end   = int(len(obj_minus_sky) - height_correction+.5)

			sky_corrected_lightcurve = obj_minus_sky[ast_start:ast_end] / row_avgs_smooth # this is the actual sky correction 
			# sky_corrected_lightcurve = obj_minus_sky / row_avgs_smooth

			# ax[1].errorbar(np.arange(len(obj_minus_sky)), obj_minus_sky, yerr = sigma_row, fmt='g', capsize=3, linewidth=2, elinewidth=1, alpha=.8)
			# ax[1].plot(np.arange(len(obj_minus_sky)), obj_minus_sky, 'b', label='transparency corrected', linewidth=3)
			# ax[1].legend()

			# fig_star_avg, ax_star_avg = plt.subplots()
			# ax_star_avg.set_title('average star lightcurve')
			# ax_star_avg.plot(np.arange(len(row_avgs_smooth)) , row_avgs_smooth)

			
			# norm_ast_lightcurve = obj_minus_sky/ast_norm 
			# norm_ast_lightcurve = norm_ast_lightcurve[ast_start:ast_end]


			# light_curve = lightcurves[i]
			x = np.linspace(start_time, start_time + exp_time/(60*60*24), len(sky_corrected_lightcurve))
			# ax_ast.plot(x, norm_ast_lightcurve)

			lightcurves.append(sky_corrected_lightcurve)
			start_times.append(x)

			print()
			file.close()

			# ax[0].legend()


		indices     = np.array ([len(i) for i in lightcurves])
		lightcurves = np.hstack(np.array(lightcurves, dtype=object))
		start_times = np.hstack(np.array(start_times, dtype=object))
		# f_err       = np.random.random(size=lightcurves.shape)

		# frequency, power = LombScargle(start_times, lightcurves).autopower()

		# peak_frequency = frequency[np.argmax(power)]
		# peak_period    = 1/peak_frequency * 24 * 3600
		# print('peak period: ', peak_period )

		directory_name = d.split('/')[1]

		np.savetxt(f'./output/{directory_name}.txt', np.array([start_times, lightcurves]).T)
		np.savetxt(f'./output/{directory_name}_indices.txt', indices)



		# plt.show()
	# output.close()

