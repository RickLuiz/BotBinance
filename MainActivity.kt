package com.example.sheetapp

import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import okhttp3.*
import java.io.IOException

class MainActivity : AppCompatActivity() {

    private val client = OkHttpClient()
    private val baseUrl = "http://192.168.0.19:8000"  // Troque pelo seu IP local

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val btnSend = findViewById<Button>(R.id.btnSend)
        val txtOutput = findViewById<TextView>(R.id.txtOutput)
        val inputData = findViewById<EditText>(R.id.inputData)

        // Fazer GET na inicialização
        getData(txtOutput)

        btnSend.setOnClickListener {
            val text = inputData.text.toString()
            postData(text, txtOutput)
        }
    }

    private fun getData(output: TextView) {
        val request = Request.Builder()
            .url("$baseUrl/read")  // Endpoint FastAPI
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                output.post { output.text = "Erro: ${e.message}" }
            }

            override fun onResponse(call: Call, response: Response) {
                val responseData = response.body?.string()
                output.post { output.text = "Dados: $responseData" }
            }
        })
    }

    private fun postData(data: String, output: TextView) {
        val json = """{"dado": "$data"}"""

        val body = RequestBody.create("application/json".toMediaTypeOrNull(), json)
        val request = Request.Builder()
            .url("$baseUrl/write")  // Endpoint FastAPI
            .post(body)
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                output.post { output.text = "Erro ao enviar: ${e.message}" }
            }

            override fun onResponse(call: Call, response: Response) {
                output.post { output.text = "Resposta: ${response.body?.string()}" }
            }
        })
    }
}
