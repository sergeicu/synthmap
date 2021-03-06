# RUN JULIA WITH ARGV - works with real data (from clinic) and synthetic data

import os 
import glob 
import argparse
import shutil

import nibabel as nb 
import numpy as np
import nrrd 
import hdf5storage as hdf

import svtools as sv

def load_args(): 
    parser = argparse.ArgumentParser()

    parser.add_argument('--input', type=str, required=True, nargs="+", help='input file, folder or regexp')
    parser.add_argument('--out', type=str, required=True, help='output folder name')
  
    parser.add_argument('--ext', type=str, choices=['.nii.gz', '.nii', '.nrrd'], default='.nii.gz', help='define extension of the files')
    parser.add_argument('--prefix', type=str, default='', help='define prefix of the file name. Only works if directory is specified')
    parser.add_argument('--suffix', type=str, default='', help='define suffix of the file name. Only works if directory is specified')

    parser.add_argument('--cut_off_echo', type=int, default=14, help='define which echo to cut off during MWF calculation')

    parser.add_argument('--overwrite_old_files', action="store_true", help='re-run Julia on all files that have already been processed (this is time consuming step). Else - it skips already computed results ONLY on files that already exist.')
    
    parser.add_argument('--recalculate_cutoff', action='store_true', help='recalculate cut off echo for files where the T2 distribution had already been computed by Julia. ')

    parser.add_argument('--matlab', action='store_true', help='output a command to run in the matlab implementation of the same algorithm.')    
    
    parser.add_argument('--debug', action="store_true", help='run with args defined in load_debug_args')
    
    args = parser.parse_args()
    
    if args.debug:
        args = load_debug_args()
        
    return args 


def load_debug_args():

    # load default args 
    # n/a # args = load_args()
    
    # prompt user to proceed  
    input('Debug is true, please press any button to continue')
    
    # initialize argparse object
    args = sv.init_argparse()

    # overwrite default arguments  
    dataset = 2
    
    # automatically preprocessed data from my scripts (however files do not look good because they were )
    if dataset == 1: 
        experiment= '/home/ch215616/abd/mwf_data/TEMP_real_data_10subjects/'
        folder = 'ALL_corrected_nii_resampled_normalized_rescaled_slices/'
        file = 'case001_50.20151105.Myelin_4concat.xse2d32_0019.nii.gz'
    elif dataset == 2: 
        experiment= '/home/ch215616/abd/mwf_data/real_data_10subjects/'
        folder = 'ALL_corrected_renamed_nii_slices_resample_normalized/'       
        file = '22_s22.nii.gz'
        
    args.input = [experiment + folder + file]
    
    args.out = '/home/ch215616/abd/mwf_data/TEMP_run_julia_output/'
    
    args.prefix = ''
    args.suffix = ''
    args.ext = '.nii.gz'
    args.cut_off_echo = 13
    
    return args 

def get_data_paths(args): 

    # if one element in a list 
    if len(args.input)==1:
        args.input = args.input[0] # if only one item is supplied in a list - turn into a string 

        assert os.path.exists(args.input), f"Incorrect test input"

        # if path to folder 
        if os.path.isdir(args.input):
            args.input = args.input + "/" if not args.input.endswith("/") else args.input 
            input_paths = sorted(glob.glob(args.input+args.prefix+"*" + args.suffix + "*" + args.ext))
            assert input_paths, f"glob.glob returned empty list. Check input specifications"
            
        # if path to file 
        elif os.path.isfile(args.input):
            input_paths = [args.input]
    else: 
        # if many elements in a list of inputs 
        input_paths = args.input

    return input_paths  

def format_output(args):
    
    # assert that input folder is not the same as output folder (since the files are not renamed) 
    if isinstance(args.input,str): 
        input_dir = os.path.dirname(args.input)
        if not args.matlab:
            assert input_dir != os.path.dirname(args.out), f"Output folder cannot be the same as folders in which the input files are hosted"
        
    elif isinstance(args.input, list): 
        for f in args.input: 
            input_dir = os.path.dirname(f+"/")
            if not args.matlab:
                assert input_dir != os.path.dirname(args.out), f"Output folder cannot be the same as folders in which the input files are hosted\n input_dir: {input_dir}\n output_dir {os.path.dirname(args.out)}"
            
            
    # make the directory and output correct path
    args.out = args.out + "/" if not args.out.endswith("/") else args.out    
    os.makedirs(args.out, exist_ok=True)
    print(f"Files to be saved to: {args.out}")
    
    return args.out      
   
    
def process_julia(args, impaths, juliadir, fullname):

    if not args.overwrite_old_files: 
        # check which files have already been processed. 
        # If julia output already exists for them - check args whether to skip or not 
        improcessed = [i for i in impaths if os.path.exists(i.replace(".nii.gz", ".t2dist.mat"))]
        print(f"Skipping already pre-processed files: {len(improcessed)} files")
        
        impaths = [i for i in impaths if not os.path.exists(i.replace(".nii.gz", ".t2dist.mat"))]
        
    
    with open(fullname,'w') as f:

        # write file names 
        for impath in impaths:
            f.write(impath+'\n')

        f.write('--output'+'\n')
        f.write(args.outdir+'\n')
        f.write('--T2map'+'\n')
        f.write('--T2part'+'\n')
        f.write('--TE'+'\n')
        f.write('9e-3'+'\n')
        f.write('--nT2'+'\n')
        f.write('40'+'\n')
        f.write('--T2Range'+'\n')
        f.write('10e-3'+'\n')
        f.write('2.0'+'\n')
        f.write('--SPWin'+'\n')
        f.write('10e-3'+'\n')
        f.write('50e-3'+'\n')
        f.write('--MPWin'+'\n')
        f.write('50e-3'+'\n')
        f.write('200e-3'+'\n')

    # executes the files written to .txt file
    print('To execute: run the following:\n')
    cmd1 = 'export JULIA_NUM_THREADS=4;'
    print(cmd1)
    cmd2 = ['julia', juliadir+'decaes.jl', '@'+fullname]
    print(' '.join(cmd2) )

    return cmd2


def add_dimension(args,f):
    """ insert a new dimension into a nifti file if it's a 2D slice 
    
    i.e. (192,160,32) -> (192,160,1,32)
    """    
    # Define new name 
    fnew = args.outdir+os.path.basename(f)
    
    if not os.path.exists(fnew) or args.overwrite_old_files: 
        
        # load image 
        imo = nb.load(f)
        im = imo.get_fdata()

        # Perform key checks 
        assert im.shape[-1] == 32, f"The last dimension of the image has to be equal to number of echoes - 32. It is {im.shape}"
        assert 4 >= im.ndim >= 3, f"Image must have 3 or 4 dims (x,y,z,echoes) or (x,y,echoes)"

        assert not np.any(im[im<0]), "there are negative values in this nifti - please correct them asap"


        # if image has 3 dimensions,we must add extra dimension  
        if im.ndim == 3: 
            # expand the slice dimension
            im = np.expand_dims(im,axis=2)
            imo.header.set_data_dtype(np.float32) # THIS IS CRUCIAL TO PROCESSING! 
            imnew = nb.Nifti1Image(im,affine=imo.affine, header=imo.header)
            imnew.header.set_data_shape(im.shape)

            # create new file  
            nb.save(imnew,fnew)    

        # else copy file to output folder directly 
        else: 
            shutil.copyfile(f, fnew)


    return fnew 

    
def convert_julia_mat_to_nii(args,t2dist_mat_path,nii_ref_path, cutoff):
        
    pT2 = hdf.loadmat(t2dist_mat_path)['dist']
    pT2 = np.nan_to_num(pT2)
    
    mw1=np.sum(pT2[:,:,:,0:args.cut_off_echo],3)    
    tot1=np.sum(pT2[:,:,:,0:39],3)
    mwf=np.divide(mw1,tot1, out=np.zeros_like(mw1), where=tot1!=0)  #c = np.divide(a, b, out=np.zeros_like(a), where=b!=0)
    
    # convert to nifti with a reference 
    refo = nb.load(nii_ref_path)
    header = refo.header.copy()
    header.set_data_shape(np.squeeze(mwf).shape)
    imnewo = nb.Nifti1Image(mwf,affine=refo.affine,header=header)
    savename = nii_ref_path.replace('.nii.gz','_julia_mwf'+'_e'+str(args.cut_off_echo)+'_'+str(int(cutoff))+'ms'+'.nii.gz')
    nb.save(imnewo,savename)
    
    return savename 


################################################################
 

def get_echo_in_ms(echo):
    """ Compute timings     """ 
    
    
    """
     't2times': array([
            0.01      , 0.01145515, 0.01312205, 0.0150315 , 0.01721881,
            0.0197244 , 0.0225946 , 0.02588245, 0.02964873, 0.03396307,
            0.0389052 , 0.04456649, 0.05105158, 0.05848035, 0.06699012,
            0.07673819, 0.08790474, 0.1006962 , 0.115349  , 0.13213401,
            0.15136149, 0.17338685, 0.19861723, 0.22751901, 0.26062643,
            0.29855148, 0.34199519, 0.39176061, 0.44876764, 0.51407005,
            0.58887494, 0.67456506, 0.77272437, 0.88516734, 1.01397244,
            1.16152061, 1.33053924, 1.52415262, 1.74593964, 2.        ])}    
    """        
    T2range = np.logspace(np.log10(10), np.log10(2000), num=40)
    ms=T2range[echo-1]
    
    return ms 
    
        
################################################################
# Prasloski implementation in matlab 


def convert_image_for_prasloski_matlab(impath):

    """Convert image into .nrrd format to be processed by the default matlab code shared by Onur"""
    
    im_o = nb.load(impath)
    im = im_o.get_fdata()
    im_r = np.moveaxis(im,[-1],[0])
    im_r_sc = im_r
    im_r_sc_uint16 = im_r_sc.astype('uint16')
    savename = impath.replace('.nii.gz','_rescaled_reshaped_uint16.nrrd')
    nrrd.write(savename, im_r_sc_uint16)
    
    if debug: 
        print(f"Saved file ready for Prasloski processing to\n{savename}")
        print('WARNING: this file is not viewable in itksnap')


def generate_code_to_run_prasloski(impath, multifile=False, debug=False): 

    """Generate snippet of matlab code to run analysis on this particular subject. 
    
    Args: 
        impath (str): full path to original file generated with forward model. e.g. mwf_0_linspaced_FA144_echoes.nii.gz
    
    """
    
    dirname, fname = os.path.split(impath)
    converted_name = fname.replace('.nii.gz','_rescaled_reshaped_uint16.nrrd')
    
    cmd1 = "folder = '"+dirname+"/';"
    
    if not multifile:
        cmd2 = "batch_run_myelin({[folder,'"+converted_name+"']});"    
    
    else: 
        cmd2 = ["f1=[folder,'/"+converted_name+"'];"]
        cmd2.append("\nInput = {f1};")
        cmd2.append("\nbatch_run_myelin(Input);")
        cmd2 = ''.join(cmd2)
    
    print(cmd1)
    print(cmd2)


def fix_prasloski_header(impath,refpath):
    
    im = nb.load(impath).get_fdata()
    refo = nb.load(refpath)    
        
    imnewo = nb.Nifti1Image(im,affine=refo.affine,header=refo.header)
    savename = impath.replace(".nii.gz","_hdr.nii.gz")
    nb.save(imnewo,savename)    
    

################################################################



if __name__ == '__main__':

    
    # load args  
    debug = False
    args = load_args() if not debug else load_debug_args()                        
    # set input and output paths 
    input_paths = get_data_paths(args)
    args.outdir = format_output(args)

    # python part 
    if not args.matlab: 
    
        # set julia dir 
        juliadir = '/home/ch215616/w/code/mwf/ext/julia/mwiexamples/'

        # STEP 1 - insert new dimensions as slice dimension (required by julia)
        input_paths = [add_dimension(args,path) for path in input_paths]


        # STEP 2 - run julia from .txt file 
        txt_file = input_paths[0].replace('.nii.gz','.txt') if len(input_paths) == 1 else args.out +'run_julia.txt'
        cmd = process_julia(args, input_paths, juliadir, txt_file)
        if not args.recalculate_cutoff: # do not run julia if we are only recalculating the cutoff value for existing files
            sv.execute(cmd)        

        # STEP 3 - convert julia .mat output into .nii.gz files 
        niftis = [] 
        L = len(input_paths)
        cutoff = get_echo_in_ms(args.cut_off_echo)
        for i, path in enumerate(input_paths):
            print(f"{i}/{L}")
            mat_file = path.replace('.nii.gz','.t2dist.mat')
            niftis.append(convert_julia_mat_to_nii(args,mat_file,path,cutoff))

        # STEP 4 - rescale julia output by 100 (for easier comparison with synthNet output)
        for i, nii in enumerate(niftis):
            print(f"{i}/{L}")
            imo = nb.load(nii)
            im = imo.get_fdata()
            im = np.multiply(im,100)
            imnewo = nb.Nifti1Image(im,affine=imo.affine, header=imo.header)
            savename = nii.replace('.nii.gz','_n.nii.gz')
            nb.save(imnewo,savename)
    
    else: 
        assert os.path.isfile(input_paths[0]), f"Matlab processing is performed one slice at a time. Please specify full path to file"
        
        input(f"Output will be written to this directory: {os.path.dirname(input_paths[0])}. Proceed?")
        convert_image_for_prasloski_matlab(input_paths[0])
        
        
        generate_code_to_run_prasloski(input_paths[0])
