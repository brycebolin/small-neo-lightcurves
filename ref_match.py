import numpy as np
import astropy as ap
import matplotlib.pyplot as plt
from matplotlib import colors
from astropy.io import fits
from scipy.ndimage import rotate
from scipy.stats import mode
from scipy.optimize import curve_fit
from astropy.wcs import WCS, utils
from magic_star import point_rotation, reverse_rotation
from astropy.coordinates import SkyCoord
from astropy import units as u

def line( x , m , b): return m * x + b

def line_one ( x , b): return x + b

def quadratic ( x , a , b , c) : return a * x ** 2 + b * x + c

def exponential ( x , A , b , c): return A * np.exp(x * b) + c

# to get absolute mag and orbital information
from astroquery.jplhorizons import Horizons

plt.rcParams.update({'figure.max_open_warning': 0})

paperheight = 10
paperwidth = 13
margin = 1.0

fontsize_standard = 28

# initializing all directories
import os
from os.path import isdir, isfile, join
directory = './'	
dir_names = [directory+f+'/' for f in os.listdir(directory) if isdir(join(directory,f))] 

filt_ind = {'g':21, 'r': 25, 'i': 29}
mins = {'g':100, 'r': 150, 'i': 250}


for d in dir_names:
	lc_dirs = [d+f for f in os.listdir(d) if isdir(join(d,f))] 

	for ld in lc_dirs :

		if 'data/LCLIST' in ld or 'git' in ld: continue
		# print(ld)

		lc_files = [join(ld,f) for f in os.listdir(ld) if isfile(join(ld,f))]
		# print(os.listdir(ld))
		# print( lc_files )

		for f in lc_files :
			if not 'star_params' in f: continue
			if not ('EV84' in f and 'o22' in f): continue

			fits_name = ('/'.join(f.split('/')[:-1]) + '.flt')


			try:
				fits_file = fits.open(fits_name)
				print(fits_name)
			except Exception as e:
				print(f'NO FITS FILE FOUND: {fits_name}')
				continue

			hdr = fits_file[0].header
			img = fits_file[0].data

			exp_time   = float(hdr['EXPMEAS'])
			gain       = float(hdr['GAIN'])
			rd_noise   = float(hdr['RDNOISE']) 

			star_id , ra , dec , s , L , A , b , x , y , a , flux = np.loadtxt ( f , skiprows=1 , unpack=True )

			fig , ax = plt.subplots()
			ax.set_title(fits_name)
			ax.imshow(img, cmap='gray', norm=colors.LogNorm(vmin=mins[hdr['FILTER'][0]]))

			# transforming coordinates back to original frame
			x_0 , y_0 = reverse_rotation ( x , y , np.mean(a) , img)

			# transforming ra dec to x y
			w = WCS(hdr)
			ra_dec = SkyCoord ( ra=ra*u.degree , dec=dec*u.degree )
			# x_ , y_ = utils.skycoord_to_pixel ( SkyCoord(ra=ra*u.degree , dec=dec*u.degree) , w )


			# refcat magic
			# RA, Dec, g, r, i, z, J, cyan, orange.
			# using -all: 
			#   RA             Dec      plx  dplx    pmra dpmra   pmdec dpmdec Gaia  dGaia   BP   dBP     RP    dRP   Teff AGaia dupvar Ag rp1     r1    r10    g   dg  gchi gcontrib r   dr  rchi rcontrib i   di  ichi icontrib z   dz  zchi zcontrib nstat J   dJ     H     dH     K     dK

			refcat = []

			args_str = f'./refcat {np.mean(ra_dec.ra.deg)} {np.mean(ra_dec.dec.deg)} -rad 1 -dir 00_m_16/ -all'
			print ( 'refcat call to terminal: ' , args_str )
			ref_stars = np.array(os.popen(args_str).read().split('\n')[1:-1])
			for j in ref_stars:
				refcat.append(np.array(j.split(), dtype=float))
			refcat = np.array(refcat)
			# print(refcat.shape)
			# end refcat magic

			# if True: break

			ref_ra_dec = SkyCoord ( ra=refcat[:,0]*u.degree , dec=refcat[:,1]*u.degree)

			idx , d2d , d3d = ra_dec.match_to_catalog_sky (ref_ra_dec , nthneighbor=1)

			fig_1 , ax1 = plt.subplots(figsize=((paperwidth*1.15) - 2 * margin, (paperheight*1.15) - 2 * margin) )
			ax1.hist ( d2d.arcsec , bins=np.linspace(0 , 200 , 51) , range=[0,200] )
			hist , bins  = np.histogram(d2d.arcsec , bins=np.linspace(0 , 200 , 51) , range=[0,200])
			# ax1.set_xlabel('offset in arcsec')

			# basically converting bins --> integers so we find the mode. digitize gives me the index of which bin each d2d goes into
			# to be fair this is from stack overflow and it might be sketchy and untested
			binsd = bins[np.digitize ( d2d.arcsec , bins , right=False )-1] 
			# print(binsd)

			bins_mode = mode ( binsd  )[0]
			mode_err  = 2
			print(f'Mode offset: {bins_mode[0]} +/- {mode_err}')
			
			# now we constrain the offsets by +/- 1" around mode offset
			dist_filter = np.where ( (d2d.arcsec <= bins_mode + mode_err) & (d2d.arcsec >= bins_mode - mode_err)  )
			print(f'+/- 2" from mode offsets in arcsec: {d2d.arcsec[dist_filter]}')

			matches = ref_ra_dec[idx[dist_filter]]

			ref_x , ref_y = utils.skycoord_to_pixel(matches , w)
			x_0_matches = x_0[dist_filter]
			y_0_matches = y_0[dist_filter]


			fig_angle, ax_angle = plt.subplots(figsize=((paperwidth*1.15) - 2 * margin, (paperheight*1.15) - 2 * margin) )
			ax_angle.hist ( d3d.value,  bins=np.linspace(0 , 1e-3 , 51) )

			angle = np.arctan2 ( ref_y-y_0_matches , ref_x-x_0_matches ) # arctan2(x , y) --> atan(x/y)
			print(angle*180/np.pi)
			# fig_angle, ax_angle = plt.subplots(figsize=((paperwidth*1.15) - 2 * margin, (paperheight*1.15) - 2 * margin) )
			ax_angle.hist ( angle*180/np.pi , bins=np.linspace(0 , 90 , 91) )
			histA , bins_A  = np.histogram(angle*180/np.pi , bins=np.linspace(0 , 90 , 91) )

			binsA = bins_A[np.digitize ( angle*180/np.pi , bins_A , right=True ) ] 
			print(binsA)

			binsA_mode = mode ( binsA  )[0]
			modeA_err  = 3
			print(f'Mode offset: {binsA_mode[0]} +/- {modeA_err}')
			
			angle_filter = np.where( (angle <= binsA_mode + modeA_err) & (angle >= binsA_mode - modeA_err) )

			print(angle[angle_filter])

			ax.hist ( angle[angle_filter] , label='filtered' )
			# print()
			# print(matches)
			# print()
			# print(ref_ra_dec[idx[dist_filter] [angle_filter]])

			ax.scatter ( ref_x  , ref_y , label='ref matches'  )
			ax.scatter ( x_0[dist_filter], y_0[dist_filter] , label='My stars matches')
			# ax.scatter ( x_0, y_0 , label='All my stars')

			# ax.scatter ( x_0[idx_[dist_filter_]] , y_0[idx_[dist_filter_]] , label='My stars')

			g_mag = refcat[idx[dist_filter]] [ :, 21 ]
			r_mag = refcat[idx[dist_filter]] [ :, 25 ]
			i_mag = refcat[idx[dist_filter]] [ :, 29 ]

			g_r = g_mag-r_mag
			r_i = r_mag-i_mag


			# dont implement this fully just yet! i need more solar analogs lmfao
			color_filter = np.where( (g_r >= .35) & (g_r <= .5) & (r_i >= .05) & (r_i <= .15) )

			print( 'g-r colors: ' , g_r[color_filter] )
			print( 'r-i colors: ' , r_i[color_filter] )


			instrumental_mag = -2.5*np.log10(flux)     [dist_filter] [ color_filter ]
			instrumental_err = 1.08574 * (flux ** -.5) [dist_filter] [ color_filter ]
			ref_mag =  refcat[idx[dist_filter]] [:,filt_ind[hdr['FILTER'][0]]]
			ref_err =  refcat[idx[dist_filter]] [:,filt_ind[hdr['FILTER'][0]]+1]

			ref_mag = ref_mag[ color_filter ]
			ref_err = ref_err[ color_filter ]

			print(instrumental_mag.shape , ref_mag.shape)

			# instrumental_mag = -2.5*np.log10(flux)
			# instrumental_err = 1.08574 * (flux ** -.5)
			# ref_mag =  refcat[idx[dist_filter]] [:,filt_ind[hdr['FILTER'][0]]]
			# ref_err =  refcat[idx[dist_filter]] [:,filt_ind[hdr['FILTER'][0]]+1]

			fig_cal , ax_cal = plt.subplots(figsize=((paperwidth*1.15) - 2 * margin, (paperheight*1.15) - 2 * margin) )
			ax_cal .errorbar ( instrumental_mag , ref_mag , ref_err , instrumental_err , fmt='s' , markerfacecolor='blue' , markeredgecolor='black' , ecolor='black' , capthick=2 , markersize=7 , capsize=3  )
			plt.show()

			param , param_cov = curve_fit ( line , instrumental_mag , ref_mag, sigma=ref_err , absolute_sigma=True )
			print('general line: ', param , np.diag(param_cov)**.5)
			ax_cal.plot (instrumental_mag , line(instrumental_mag , *param) , label=f'y={param[0]:.1f}x + {param[1]:.1f}')

			param_one , one_cov = curve_fit ( line_one , instrumental_mag , ref_mag , sigma=ref_err , absolute_sigma=True  )
			print( 'line slope one: ',  param_one[0] , np.diag(one_cov)[0]**.5)
			ax_cal.plot (instrumental_mag , line_one(instrumental_mag , *param_one) , label=f'y=x + {param_one[0]:.1f}')

			param_quad , cov_quad = curve_fit ( quadratic , instrumental_mag[dist_filter] , ref_mag , sigma=ref_err , absolute_sigma=True  )
			print( 'quadratic params and uncertainties ',  param_quad , np.diag(cov_quad)**.5)
			# ax_cal.plot (np.linspace(instrumental_mag[dist_filter].min() , instrumental_mag[dist_filter].max() ,50 ) , quadratic(np.linspace(instrumental_mag[dist_filter].min() , instrumental_mag[dist_filter].max() , 50 ), *param_quad) )


			print('image filter: ', hdr['FILTER'][0])

			ax.legend()
			ax_cal.legend()
			plt.tight_layout()
			print()



		plt.show()


		# if True: break
