# You need to install pyaudio to run this example
# pip install pyaudio

# When using a microphone, the AudioSource `input` parameter would be
# initialised as a queue. The pyaudio stream would be continuosly adding
# recordings to the queue, and the websocket client would be sending the
# recordings to the speech to text service

import time

import pyaudio

from ibm_watson import SpeechToTextV1
from ibm_watson.websocket import RecognizeCallback, AudioSource
from threading import Thread
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator

import queue
from queue import Empty

try:
    from Queue import Queue, Full
except ImportError:
    from queue import Queue, Full

###############################################
#### Initalize queue to store the recordings ##
###############################################


class stt_watson(object):

    CHUNK = 1024
    # Note: It will discard if the websocket client can't consumme fast enough
    # So, increase the max size as per your choice
    BUF_MAX_SIZE = CHUNK * 10
    # Buffer to store audio
    q = Queue(maxsize=int(round(BUF_MAX_SIZE / CHUNK)))

    # Variables for recording the speech
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 44100

    # modifying IBM's class so it can be restarted
    # https://github.com/watson-developer-cloud/python-sdk/blob/master/ibm_watson/websocket/audio_source.py
    class AudioSource2(AudioSource):
        def restart_recording(self):
            self.is_recording = True

    # define callback for the speech to text service
    class MyRecognizeCallback(RecognizeCallback):
        def __init__(self, q):
            RecognizeCallback.__init__(self)
            self.transcript = "no transcript"
            self.q = q

        def on_transcription(self, transcript):
            pass

        def on_connected(self):
          # print('Connection was successful')
            pass

        def on_error(self, error):
          print('Error received: {}'.format(error))
          self.q.put((True, self.transcript))

        def on_inactivity_timeout(self, error):
          print('Inactivity timeout: {}'.format(error))
          self.q.put((True, self.transcript))
          #thread.exit()

        def on_listening(self):
          print('Watson STT is listening')

        def on_hypothesis(self, hypothesis):
          # print("hypo: " + hypothesis)
          pass

        def on_data(self, data):
          result = data['results'][0]['alternatives'][0]['transcript']
          final = data['results'][0]['final']
          self.transcript = result
          self.q.put((final, result))
          if (final):
            print("final: " + result)
          else:
            print("interim: " + result)

        def on_close(self):
          print("Connection closed")
          self.q.put((True, self.transcript))
          #thread.exit()




    def __init__(self, iamkey, url):
        # if url == "" or url == "default":
        #   url = "https://stream.watsonplatform.net/speech-to-text/api"
        # print("url: " + url)
        #print("key: " + iamkey)
        # self.speech_to_text = SpeechToTextV1(
        #   iam_apikey=iamkey,
        #   url=url)
        authenticator = IAMAuthenticator(iamkey)
        # if url == "" or url == "default":
        #   url = "https://stream.watsonplatform.net/speech-to-text/api"
        self.speech_to_text = SpeechToTextV1(authenticator=authenticator)
        # Create an instance of AudioSource
        # self.audio_source = AudioSource(self.q, True, True)
        self.audio_source = self.AudioSource2(self.q, True, True)
        # instantiate pyaudio
        self.audio = pyaudio.PyAudio()

    ###############################################
    #### Prepare the for recording using Pyaudio ##
    ###############################################
      # define callback for pyaudio to store the recording in queue


    def pyaudio_callback(self, in_data, frame_count, time_info, status):
        try:
            self.q.put(in_data)
        except Full:
            pass  # discard
        return (None, pyaudio.paContinue)

    # this function will initiate the recognize service and pass in the AudioSource
    def recognize_using_weboscket(self, q, audio_source, lang, timeout):
        mycallback = self.MyRecognizeCallback(q)
        time_limit = int(timeout + 2)
        print("time limit: " + str(time_limit))
        try:
            self.speech_to_text.recognize_using_websocket(audio=audio_source,
                                                     content_type='audio/l16; rate=44100',
                                                     model=lang,
                                                     input_device_index=1,
                                                     recognize_callback=mycallback,
                                                     interim_results=True,
                                                     inactivity_timeout=time_limit)
        except:
            print("Waston STT thread ended")

      ###############################################
      #### Initiate recognition ########
      ###############################################
    def transcribe(self, lang, time_limit):
        # open stream using callback
        # audio_source = AudioSource(self.q, True, True)
        # audio = pyaudio.PyAudio()

        self.audio_source.restart_recording()

        stream = self.audio.open(
            input_device_index = 1,
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            frames_per_buffer=self.CHUNK,
            stream_callback=self.pyaudio_callback,
            start=False
        )

        # https://cloud.ibm.com/docs/services/speech-to-text?topic=speech-to-text-models
        if lang == "" or lang == "default" or lang == "enUS":
          lang = "en-US_BroadbandModel"
        elif lang == "enGB":
          lang = "en-GB_BroadbandModel"
        elif lang == "deDE":
          lang = "de-DE_BroadbandModel"
        elif lang == "esES":
          lang = "es-ES_BroadbandModel"
        elif lang == "frFR":
          lang = "fr-FR_BroadbandModel"
        else:
          lang = "en-US_BroadbandModel"

        #########################################################################
        #### Start the recording and start service to recognize the stream ######
        #########################################################################
        stream.start_stream()

        q = queue.Queue(maxsize=int(round(self.BUF_MAX_SIZE / self.CHUNK)))
        transcript = "no transcription"
        print("starting transcription...")
        try:
          recognize_thread = Thread(target=self.recognize_using_weboscket, args=(q,self.audio_source, lang, time_limit))
          #recognize_thread.setDaemon(True)
          recognize_thread.start()
          #self.recognize_using_weboscket(q,self.audio_source, lang, timeout)
          timeout = time.time() + time_limit
          print(time.time())
          #transcript = "no transcription"
          status = False
          while status == False and time.time() < timeout:
            try:
              message = q.get(False)
              if message != None:
                #print(message[0],message[1])
                if message[0]:
                    status = True
                transcript = message[1]
            except Empty:
            #except:
              pass
            time.sleep(0.001)
          print(timeout,"time is up...")
        except BaseException as e:
        #except:
          print('Error: ' + str(e))
          print("all done...")
        finally:
          print("shutting down")
          # stream.stop_stream()
          # stream.close()
          # self.audio.terminate()
          # self.audio_source.completed_recording()

        return transcript