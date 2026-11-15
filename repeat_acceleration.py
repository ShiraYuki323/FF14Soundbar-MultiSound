"""Consecutive successful skill-slot playback; no input polling or audio I/O."""


class RepeatAcceleration:
    def __init__(self):self.reset()

    def reset(self):
        self.index=None;self.at=None;self.rate=1.0

    def next_rate(self,index,now,window=5.0):
        if self.index==index and self.at is not None and 0<=now-self.at<=window:
            return round(min(1.6,self.rate+.1),2)
        return 1.0

    def accept(self,index,now,rate):
        self.index=index;self.at=now;self.rate=rate
