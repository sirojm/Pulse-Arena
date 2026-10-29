package id.pulsearena.controller;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.provider.DocumentsContract;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.URI;

/**
 * Native Android client for the Windows-based PULSE ARENA MIDI/OSC bridge.
 * Does not send OSC by itself. The Windows bridge sends UDP OSC / virtual MIDI.
 */
public class MainActivity extends Activity {
    private final int BACKGROUND=Color.rgb(10,18,25), GREEN=Color.rgb(109,234,168);
    private WebView web;
    private LinearLayout entry;
    private EditText host;
    private ValueCallback<Uri[]> fileCallback;
    private String pendingJson;
    private String serverHost;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(BACKGROUND);
        getWindow().setNavigationBarColor(BACKGROUND);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        showConnection();
    }
    private int dp(int value) {return Math.round(getResources().getDisplayMetrics().density*value);}
    private GradientDrawable panel(int color,int stroke,int radius) {
        GradientDrawable bg=new GradientDrawable();bg.setColor(color);bg.setCornerRadius(dp(radius));bg.setStroke(dp(1),stroke);return bg;
    }
    private TextView text(String content,int size,int color) {
        TextView t=new TextView(this);t.setText(content);t.setTextSize(size);t.setTextColor(color);t.setGravity(Gravity.CENTER_HORIZONTAL);return t;
    }
    private void showConnection() {
        if(web!=null){web.destroy();web=null;}
        LinearLayout base=new LinearLayout(this);base.setOrientation(LinearLayout.VERTICAL);base.setGravity(Gravity.CENTER);
        base.setPadding(dp(25),dp(24),dp(25),dp(24));base.setBackgroundColor(BACKGROUND);
        TextView emblem=text("▦",64,GREEN);base.addView(emblem);
        TextView title=text("PULSE  ARENA",30,Color.WHITE);title.setTypeface(null,Typeface.BOLD);
        LinearLayout.LayoutParams titleLp=new LinearLayout.LayoutParams(-1,-2);titleLp.topMargin=dp(4);base.addView(title,titleLp);
        TextView sub=text("LIVE MIDI / OSC TOUCH CONTROL",11,GREEN);sub.setLetterSpacing(.18f);
        LinearLayout.LayoutParams subLp=new LinearLayout.LayoutParams(-1,-2);subLp.bottomMargin=dp(45);base.addView(sub,subLp);
        TextView desc=text("Hubungkan controller ke Windows bridge pada jaringan Wi-Fi/LAN yang sama.",14,Color.rgb(161,183,191));
        LinearLayout.LayoutParams descLp=new LinearLayout.LayoutParams(-1,-2);descLp.bottomMargin=dp(22);base.addView(desc,descLp);
        host=new EditText(this);host.setSingleLine(true);host.setTextSize(19);host.setTextColor(Color.WHITE);
        host.setHintTextColor(0xff7a929e);host.setHint("192.168.1.10");host.setInputType(1);
        host.setPadding(dp(17),dp(12),dp(17),dp(12));host.setGravity(Gravity.CENTER);
        host.setText(getPreferences(0).getString("host", ""));
        host.setBackground(panel(0xff172833,0xff3d665e,12));
        LinearLayout.LayoutParams inputLp=new LinearLayout.LayoutParams(-1,dp(57));inputLp.bottomMargin=dp(16);base.addView(host,inputLp);
        Button connect=new Button(this);connect.setText("CONNECT TO RESOLUME BRIDGE");connect.setAllCaps(false);
        connect.setTextColor(BACKGROUND);connect.setTextSize(13);connect.setTypeface(null,Typeface.BOLD);
        connect.setBackground(panel(GREEN,GREEN,11));base.addView(connect,new LinearLayout.LayoutParams(-1,dp(56)));
        connect.setOnClickListener(v->{
            String raw=host.getText().toString().trim();
            if(!validPrivateHost(raw)){Toast.makeText(this,"Masukkan IP private LAN, contoh 192.168.1.10",Toast.LENGTH_LONG).show();return;}
            getPreferences(0).edit().putString("host",raw).apply();serverHost=raw;openBridge("http://"+raw+":8787/");
        });
        TextView help=text("Jalankan run_windows.bat di PC dahulu.\nPIN pairing tampil di jendela bridge Windows.",12,0xff718b97);
        help.setLineSpacing(dp(4),1f);LinearLayout.LayoutParams helpLp=new LinearLayout.LayoutParams(-1,-2);helpLp.topMargin=dp(26);base.addView(help,helpLp);
        entry=base;setContentView(base);
    }
    private boolean validPrivateHost(String value){
        // Require IPv4 literal, not a public IP address or arbitrary web server.
        if(!value.matches("\\d{1,3}(\\.\\d{1,3}){3}"))return false;
        String[] n=value.split("\\.");int[] a=new int[4];
        for(int i=0;i<4;i++){try{a[i]=Integer.parseInt(n[i]);}catch(Exception e){return false;}if(a[i]>255)return false;}
        return a[0]==10||(a[0]==172&&a[1]>=16&&a[1]<=31)||(a[0]==192&&a[1]==168);
    }
    @SuppressLint("SetJavaScriptEnabled")
    private void openBridge(String url) {
        web=new WebView(this);web.setBackgroundColor(BACKGROUND);
        web.getSettings().setJavaScriptEnabled(true);web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setMediaPlaybackRequiresUserGesture(true);
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setAllowContentAccess(true);
        web.getSettings().setSupportZoom(false);web.getSettings().setBuiltInZoomControls(false);
        web.getSettings().setDisplayZoomControls(false);
        web.getSettings().setMixedContentMode(android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        web.addJavascriptInterface(new FileBridge(),"PulseAndroid");
        web.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request){
                Uri uri=request.getUrl();
                boolean ok="http".equals(uri.getScheme())&&serverHost.equals(uri.getHost())&&uri.getPort()==8787;
                return !ok;
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error){
                if(request.isForMainFrame())Toast.makeText(MainActivity.this,"Bridge Windows tidak merespons. Cek IP / Wi-Fi.",Toast.LENGTH_LONG).show();
            }
        });
        web.setWebChromeClient(new WebChromeClient(){
            @Override public boolean onShowFileChooser(WebView view,ValueCallback<Uri[]> callback,FileChooserParams params){
                if(fileCallback!=null)fileCallback.onReceiveValue(null);
                fileCallback=callback;
                Intent i=new Intent(Intent.ACTION_GET_CONTENT);i.setType("application/json");i.addCategory(Intent.CATEGORY_OPENABLE);
                try {startActivityForResult(Intent.createChooser(i,"Import preset PULSE JSON"),201);return true;}
                catch(Exception e){fileCallback=null;callback.onReceiveValue(null);return false;}
            }
        });
        setContentView(web);
        web.loadUrl(url);
    }
    public final class FileBridge {
        @JavascriptInterface public void saveJSON(String json){
            if(json==null||json.length()>1000000)return;
            runOnUiThread(()->{
                pendingJson=json;
                Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);intent.setType("application/json");
                intent.putExtra(Intent.EXTRA_TITLE,"pulse-arena-v3-preset.json");
                try{startActivityForResult(intent,202);}catch(Exception e){pendingJson=null;Toast.makeText(MainActivity.this,"Gagal membuka penyimpanan",Toast.LENGTH_SHORT).show();}
            });
        }
    }
    @Override protected void onActivityResult(int requestCode,int resultCode,Intent data){
        super.onActivityResult(requestCode,resultCode,data);
        if(requestCode==201){if(fileCallback!=null){Uri[] result=resultCode==RESULT_OK&&data!=null&&data.getData()!=null?new Uri[]{data.getData()}:null;fileCallback.onReceiveValue(result);fileCallback=null;}}
        if(requestCode==202){if(resultCode==RESULT_OK&&data!=null&&data.getData()!=null&&pendingJson!=null){
            try(OutputStream out=getContentResolver().openOutputStream(data.getData())){
                if(out==null)throw new Exception("Output unavailable");out.write(pendingJson.getBytes(StandardCharsets.UTF_8));
                Toast.makeText(this,"Layout JSON berhasil disimpan",Toast.LENGTH_SHORT).show();
            }catch(Exception e){Toast.makeText(this,"Gagal menyimpan: "+e.getMessage(),Toast.LENGTH_LONG).show();}}
            pendingJson=null;
        }
    }
    @Override public void onBackPressed(){
        if(web!=null){showConnection();return;}
        super.onBackPressed();
    }
    @Override protected void onDestroy(){if(web!=null){web.destroy();web=null;}super.onDestroy();}
}
