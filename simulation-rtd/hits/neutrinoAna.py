import numpy as np
import ROOT
import matplotlib.pyplot as plt
import pandas as pd
import sys
import os
import multiprocessing as mp
import pandas as pd

ROOT.EnableImplicitMT()

def getFiles(dir):
    return [os.path.join(os.path.abspath(dir), f) for f in os.listdir(dir)]

sort_dir = "./neutrinos/sorted"
rtd_dir = "./neutrinos/rtd"
rtdf_files = getFiles(rtd_dir)

def makeSortType(sort_file):
    """
    extract meta data from the file name of the sort file
    """
    # check to see if running windows os..
    if os.name == 'nt':
        f = sort_file.split('\\')[-1].split('_')
    else:
        f = sort_file.split('/')[-1].split('_')
    isFHC = f[0] == 'FHC'
    nHC = int(f[1])
    xpos = int(f[2].split('-')[-1])
    ypos = int(f[3].split('-')[-1])
    zpos = int(f[4].split('-')[-1])
    seed = int(f[5].split('-')[-1])
    isAtZ = int(f[6].split('-')[-1]) == 1
    return [isFHC, nHC, xpos, ypos, zpos, seed, isAtZ]

def getRTDType(sort_file):
    """
    get the corresponding RTD file for this sort file
    """
    [isFHC, nHC, xpos, ypos, zpos, seed, isAtZ] = makeSortType(sort_file)
    typ = "FHC" if isFHC else "RHC"
    f = f"{typ}_{nHC}_x-{xpos}_y-{ypos}_z-{zpos}_seed-{seed}_zaxis-{isAtZ:d}_sorted_rtd.root"
    for rtdf in rtdf_files:
        if f in rtdf:
            return rtdf
    print("did not find: ", f)
    return None

def RDFAna(rdf_file, xpos, ypos):
    """
    return values of interest for the makePandasDF function call here
    """
    rdf = ROOT.RDataFrame('event_tree', rdf_file)

    # make sure reasonable timescale for the neutrino events
    rdf = rdf.Filter("pixel_reset < 1e-1") 
    total_resets = rdf.Count().GetValue()
    rdf = rdf.Filter(f"pixel_x < {int(xpos/0.4)} + 40 && pixel_x > {int(xpos/0.4)} - 40")\
             .Filter(f"pixel_y < {int(ypos/0.4)} + 40 && pixel_y > {int(ypos/0.4)} - 40")
    tile_resets = rdf.Count().GetValue()
                     
    return total_resets, tile_resets

def GetRDFData(f, q):
    """
    helper for mp to get data more quickly
    """
    a = makeSortType(f)
    rtd_f = getRTDType(f)
    a.append(f)
    a.append(rtd_f)
    if rtd_f is not None:
        total_resets, tile_resets = RDFAna(rtd_f, a[2], a[3])
        a.append(total_resets)
        a.append(tile_resets)
        rdf = ROOT.RDataFrame('event_tree', f)
        rdf = rdf.Filter('hit_start_t < 1e-1') # only look for hits within reasonable time
        a.append(rdf.Sum('hit_energy_deposit').GetValue())
    else:
        a.extend([0, 0, 0])

    q.put(a)

def main():
    """
    create the output DF for analysis
    """

    sort_files = getFiles(sort_dir)
    print(f"found {len(rtdf_files)} rtd files and {len(sort_files)} sort files")

    # place holder for the completed tiles
    q = mp.Queue()
    ncpu = 20

    # pull architecture procs
    procs = [mp.Process(target=GetRDFData, args=(sort, q)) for sort in sort_files[:2000]]

    nProcs = len(procs)
    print(f"begginning processing of {nProcs} tiles.")

    completeProcs = 0
    runningProcs, qdata = [], []
    while completeProcs < nProcs:

        # fill running procs until we use all cpu cores
        while len(runningProcs) <= ncpu and len(procs) > 0:
            runningProcs.append(procs.pop())

        # ensure all of the running procs have started
        for ip, p in enumerate(runningProcs):
            if p.pid is None:
                p.start()
            elif p.exitcode is not None:
                runningProcs.pop(ip)

        # wait to get anything on the queue
        if not q.empty():
            qdata.append(q.get())
            completeProcs = len(qdata)
            print(f"Completed procs {completeProcs}, {completeProcs/nProcs*100:0.2f}%..")

    d = {'FHC':[], 'nHC':[], 'xpos':[], 'ypos':[], 'zpos':[], 'seed':[], 'atZ':[],
         'sortFile':[], 'rtdFile':[],
         'total_resets':[], 'tile_resets':[], 'energy_deposit':[]}
    for data in qdata:
        d['FHC'].append(data[0])
        d['nHC'].append(data[1])
        d['xpos'].append(data[2])
        d['ypos'].append(data[3])
        d['zpos'].append(data[4])
        d['seed'].append(data[5])
        d['atZ'].append(data[6])
        d['sortFile'].append(data[7])
        d['rtdFile'].append(data[8])
        d['total_resets'].append(data[9])
        d['tile_resets'].append(data[10])
        d['energy_deposit'].append(data[11])

    df = pd.DataFrame(data=d)
    print(df)
    df.to_csv("./neutrinoAna_tmp.csv")
    print("completed creating of neutrino df")


def UpdateSrc(df, src_dest):
    """
    get the raw file for the input sort file
    """

    nEntries = len(df)
    sort_files = df['sortFile']
    src_files = []
    for f in sort_files:
        if '\\' in f:
            f = f.split('\\')[-1]
        else:
            f = f.split('/')[-1]
        typ, nHC = f.split('_')[:2]
        src_file = f"{typ}_{nHC}.root"
        src_file = os.path.join(os.path.abspath(src_dest), src_file)
        found = os.path.isfile(src_file)
        if found:
            src_files.append(src_file)
        else:
            print("WARNING: did not find file: ", src_file)

    nSrcs = len(sort_files)
    print(f"found {nSrcs} sort files.")
    if nEntries != nSrcs:
        return -1

    # initialize
    df["src_file"] = np.nan
    df["ifileNo"] = np.nan
    df["ievt"] = np.nan
    df["lepPdg"] = np.nan
    df["lepKE"] = np.nan
    df["muonReco"] = np.nan
    df["muGArLen"] = np.nan
    df["hadTot"] = np.nan
    df["hadP"] = np.nan
    df["hadN"] = np.nan
    df["hadPip"] = np.nan
    df["hadPim"] = np.nan
    df["hadPi0"] = np.nan
    df["hadOther"] = np.nan
    df["hadCollar"] = np.nan
    df["p3lep"] = pd.Series(np.array)
    df["vtx"] = pd.Series(np.array)
    df["lepDeath"] = pd.Series(np.array)
    df["muonExitPt"] = pd.Series(np.array)
    df["muonExitMom"] = pd.Series(np.array)
    df["nFS"] = pd.Series(np.array)
    df["fsPdg"] = pd.Series(np.array)
    df["fsPx"] = pd.Series(np.array)
    df["fsPy"] = pd.Series(np.array)
    df["fsPz"] = pd.Series(np.array)
    df["fsE"] = pd.Series(np.array)
    df["fsTrkLen"] = pd.Series(np.array)

    for i, src_file in enumerate(src_files):

        typ = src_file.split("/")[-1].split("_")[0] == "FHC"
        nHC = int(src_file.split("/")[-1].split("_")[1][:-5])

        if i%500 == 0:
            print("adding entry:", i)

        tf = ROOT.TFile(src_file, "READ")
        if not hasattr(tf, "tree"):
            return df
        tt = tf.tree
        for evt in tt:
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "src_file"] = src_file
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "ifileNo"] = evt.ifileNo
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "ievt"] = evt.ievt
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "lepPdg"] = evt.lepPdg
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "lepKE"] = evt.lepKE
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "muonReco"] = evt.muonReco
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "muGArLen"] = evt.muGArLen
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "hadTot"] = evt.hadTot
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "hadP"] = evt.hadP
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "hadN"] = evt.hadN
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "hadPip"] = evt.hadPip
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "hadPim"] = evt.hadPim
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "hadPi0"] = evt.hadPi0
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "hadOther"] = evt.hadOther
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "hadCollar"] = evt.hadCollar
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "p3lep"] = pd.Series(evt.p3lep)
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "vtx"] = pd.Series(evt.vtx)
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "lepDeath"] = pd.Series(evt.lepDeath)
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "muonExitPt"] = pd.Series(evt.muonExitPt)
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "muonExitMom"] = pd.Series(evt.muonExitMom)
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "nFS"] = evt.nFS
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "fsPdg"] = pd.Series(evt.fsPdg)
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "fsPx"] = pd.Series(evt.fsPx)
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "fsPy"] = pd.Series(evt.fsPy)
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "fsPz"] = pd.Series(evt.fsPz)
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "fsE"] = pd.Series(evt.fsE)
            df.loc[(df['nHC']==nHC)&(df['FHC']==typ), "fsTrkLen"] = pd.Series(evt.fsTrkLen)
            break

    return df

if __name__ == "__main__":
    main()
