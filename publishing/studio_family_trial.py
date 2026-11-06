"""A local, manual-controls family practice check; no model calls or telemetry."""
import json
from pathlib import Path
from datetime import datetime, timezone
import uuid
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

TASKS = (
    'Use “Use buttons instead” to make a small activity pack. Find its activities and answers.',
    'Close the form and use “Continue unfinished work” to reopen a draft.',
    'In My books, find a cover, preview it, and locate Review cover. Use Guide for measured checks without an AI call.',
)


def save_trial(root, observations):
    if len(observations) != len(TASKS): raise ValueError('Record all three practice tasks.')
    rows=[]
    for task, entry in zip(TASKS,observations):
        if entry['result'] not in ('Not tried','Easy','Needed help','Could not finish'): raise ValueError('Choose a practice result.')
        note=entry.get('note','')
        if not isinstance(note,str) or len(note)>2000: raise ValueError('Keep each observation under 2000 characters.')
        rows.append({'task':task,'result':entry['result'],'note':note})
    folder=Path(root)/'data'/'family_usability_trials';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]+'.json')
    with path.open('x',encoding='utf-8') as stream:
        json.dump({'recorded_utc':datetime.now(timezone.utc).isoformat(),'inference_calls':0,'observations':rows},stream,indent=2)
    return path


class FamilyPractice(tk.Toplevel):
    def __init__(self,parent,root):
        super().__init__(parent);self.title('Try the Studio with your family')
        from word_search_creator import fit_dialog_to_screen
        from .family_studio import ScrollPage
        fit_dialog_to_screen(self,760,670,550,420)
        page=ScrollPage(self);page.pack(fill='both',expand=True)
        ttk.Label(page.body,text='Watch, then simplify',style='Family.Title.TLabel').pack(anchor='w')
        ttk.Label(page.body,text='Ask one family member to try these tasks without coaching. Note where they hesitate. This checklist makes no AI calls; notes stay on this computer. No names are needed.',wraplength=650).pack(anchor='w',pady=10)
        fields=[]
        for index,task in enumerate(TASKS,1):
            ttk.Label(page.body,text=f'{index}. {task}',wraplength=650).pack(anchor='w',pady=(12,5))
            result=tk.StringVar(self,'Not tried');ttk.Combobox(page.body,textvariable=result,values=('Not tried','Easy','Needed help','Could not finish'),state='readonly').pack(anchor='w')
            notes=ScrolledText(page.body,height=2,wrap='word');notes.pack(fill='x',pady=5)
            fields.append((result,notes))
        status=tk.StringVar(self,'Record actual observations; leaving a task as Not tried does not count as a completed trial.')
        ttk.Label(self,textvariable=status,wraplength=700,padding=10).pack(fill='x')
        def save():
            try:
                path=save_trial(root,[{'result':result.get(),'note':notes.get('1.0','end-1c')} for result,notes in fields])
                status.set('Observations saved locally: '+str(path))
            except Exception as exc: status.set(str(exc))
        buttons=ttk.Frame(self,padding=10);buttons.pack(fill='x')
        ttk.Button(buttons,text='Save observations',command=save).pack(side='left')
        ttk.Button(buttons,text='Close',command=self.destroy).pack(side='right')
